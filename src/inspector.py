"""Google Form Inspector: automatically parses form questions, field types, and entry IDs."""
import json
import re
import urllib.parse
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup


QUESTION_TYPES = {
    0: "Short answer",
    1: "Paragraph",
    2: "Multiple choice",
    3: "Dropdown",
    4: "Checkboxes",
    5: "Linear scale",
    7: "Grid",
    9: "Date",
    10: "Time",
}


def normalize_form_url(url: str, follow_redirects: bool = True) -> str:
    """Normalize Google Form URL to its standard canonical viewform URL.
    
    Handles:
    - Shortened forms.gle URLs (resolves redirect to docs.google.com)
    - formResponse endpoints -> converts to viewform
    - Query parameters and hash fragments
    """
    url = url.strip()

    # If it's a shortened forms.gle link, resolve redirect via HTTP
    if ("forms.gle/" in url or "goo.gl/" in url) and follow_redirects:
        try:
            resp = requests.get(url, allow_redirects=True, timeout=10)
            url = resp.url
        except Exception:
            pass

    # If user provided a formResponse URL, convert it to viewform for inspection
    if "/formResponse" in url:
        url = url.replace("/formResponse", "/viewform")

    # Clean query parameters for inspection base (unless prefilled)
    parsed = urllib.parse.urlparse(url)
    clean_path = parsed.path
    if not clean_path.endswith("/viewform"):
        if clean_path.endswith("/"):
            clean_path += "viewform"
        elif "/d/e/" in clean_path:
            clean_path = clean_path.rstrip("/") + "/viewform"

    clean_url = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
    return clean_url


def extract_from_prefilled_url(url: str) -> Dict[str, Any]:
    """Extract entry IDs and values from a pre-filled Google Form link."""
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)

    entries = {}
    email = None

    for key, values in query_params.items():
        if key == "emailAddress":
            email = values[0] if values else ""
        elif key.startswith("entry."):
            val = values if len(values) > 1 else (values[0] if values else "")
            entries[key] = {
                "id": key,
                "title": f"Field ({key})",
                "type": "Prefilled field",
                "prefilled_value": val,
                "required": False,
                "options": []
            }

    clean_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return {
        "form_url": clean_base,
        "email": email,
        "fields": entries
    }


def _find_questions_list(elem: Any) -> List[Any]:
    """Recursively search for the list of question items in Google Form data."""
    if not isinstance(elem, list):
        return []

    # Check if this list itself is a collection of question items:
    # A question item is a list of length >= 5 where item[0] is int and item[4] is list of sub-entries
    candidate = []
    for item in elem:
        if isinstance(item, list) and len(item) >= 5 and isinstance(item[0], int) and isinstance(item[4], list):
            candidate.append(item)
    if candidate:
        return candidate

    # Otherwise search sub-lists (e.g. data[1][1])
    for item in elem:
        if isinstance(item, list):
            found = _find_questions_list(item)
            if found:
                return found

    return []


def extract_form_images(soup: BeautifulSoup):
    """Extract question-level images and option-level images from Google Form DOM."""
    question_images = {}
    option_images_by_text = {}
    option_images_by_index = {}

    items = soup.find_all("div", role="listitem")
    for it in items:
        heading = it.find("div", role="heading")
        if not heading:
            continue
        q_title_clean = heading.get_text(strip=True).rstrip("*").strip().lower()

        opt_list = []
        for img in it.find_all("img"):
            src = img.get("src", "")
            if not src or "googlelogo" in src or "cleardot" in src or src.startswith("data:image/svg"):
                continue

            opt_text = None
            curr = img.parent
            while curr and curr != it:
                classes = curr.get("class", [])
                if any("Toggle" in c or "Radio" in c or "Checkbox" in c or "Option" in c or "choice" in c.lower() for c in classes) or curr.get("role") in ["radio", "checkbox"]:
                    opt_text = curr.get_text(strip=True)
                    break
                curr = curr.parent

            if opt_text:
                clean_opt = opt_text.strip().lower()
                option_images_by_text[(q_title_clean, clean_opt)] = src
                opt_list.append(src)
            else:
                if q_title_clean not in question_images:
                    question_images[q_title_clean] = src

        if opt_list:
            option_images_by_index[q_title_clean] = opt_list

    return question_images, option_images_by_text, option_images_by_index


def parse_form_html(html: str) -> Dict[str, Any]:
    """Parse Google Form HTML and extract questions, images, and option images via FB_PUBLIC_LOAD_DATA_ and DOM."""
    fields = {}
    form_title = "Untitled Form"
    form_description = ""
    collects_email = False
    header_image = None

    soup = BeautifulSoup(html, "html.parser")
    title_elem = soup.find("meta", property="og:title")
    if title_elem and title_elem.get("content"):
        form_title = title_elem["content"]

    desc_elem = soup.find("meta", property="og:description")
    if desc_elem and desc_elem.get("content"):
        form_description = desc_elem["content"]

    # Check for header image
    for div in soup.find_all(lambda tag: tag.has_attr("style") and "background-image" in tag.get("style", "")):
        m = re.search(r'url\(["\']?(https?://[^"\')]+)["\']?\)', div["style"])
        if m:
            header_image = m.group(1)
            break

    # Check for email input in HTML
    if soup.find("input", {"name": "emailAddress"}):
        collects_email = True

    # Extract images from DOM
    q_imgs, opt_text_imgs, opt_idx_imgs = extract_form_images(soup)

    # Search for FB_PUBLIC_LOAD_DATA_
    match = re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);\s*</script>", html, re.DOTALL)
    if not match:
        return {
            "title": form_title,
            "description": form_description,
            "collects_email": collects_email,
            "header_image": header_image,
            "fields": fields
        }

    raw_json = match.group(1).strip()
    try:
        data = json.loads(raw_json)
    except Exception as e:
        return {
            "title": form_title,
            "description": form_description,
            "collects_email": collects_email,
            "header_image": header_image,
            "fields": fields,
            "error": f"Failed to decode form data: {e}"
        }

    # Locate questions list in data
    questions = []
    if len(data) > 1 and data[1]:
        questions = _find_questions_list(data[1])
    if not questions and len(data) > 0:
        questions = _find_questions_list(data)

    for item in questions:
        q_title = item[1] or "Untitled Question"
        clean_title = q_title.rstrip("*").strip().lower()
        q_desc = item[2] or ""
        q_type_code = item[3] if len(item) > 3 else -1
        q_type = QUESTION_TYPES.get(q_type_code, f"Type {q_type_code}")
        q_img = q_imgs.get(clean_title)

        # Sub-payload containing entry IDs
        sub_info = item[4]
        if not isinstance(sub_info, list) or not sub_info:
            continue

        for sub in sub_info:
            if not isinstance(sub, list) or not sub:
                continue
            entry_id_num = sub[0]
            if not entry_id_num:
                continue

            entry_key = f"entry.{entry_id_num}"
            options = []
            # sub[1] contains choices if multiple choice, dropdown, or checkboxes
            if len(sub) > 1 and isinstance(sub[1], list):
                for opt in sub[1]:
                    if isinstance(opt, list) and opt:
                        options.append(str(opt[0]))
                    elif isinstance(opt, (str, int, float)):
                        options.append(str(opt))

            # Ensure Linear scale always has options
            if q_type == "Linear scale" and not options:
                # Check if sub[3] has scale bounds e.g. [1, 5] or [1, 10]
                has_bounds = False
                if len(sub) > 3 and isinstance(sub[3], list) and len(sub[3]) >= 2:
                    try:
                        low = int(sub[3][0])
                        high = int(sub[3][1])
                        if low < high and (high - low) <= 20:
                            options = [str(i) for i in range(low, high + 1)]
                            has_bounds = True
                    except (ValueError, TypeError):
                        pass
                if not has_bounds:
                    options = [str(i) for i in range(1, 11)]

            is_required = bool(sub[2] == 1 if len(sub) > 2 else False)

            # Match option images
            opt_images = {}
            for idx, opt in enumerate(options):
                clean_o = opt.strip().lower()
                img_url = opt_text_imgs.get((clean_title, clean_o))
                if not img_url and clean_title in opt_idx_imgs and idx < len(opt_idx_imgs[clean_title]):
                    img_url = opt_idx_imgs[clean_title][idx]
                if img_url:
                    opt_images[opt] = img_url

            fields[entry_key] = {
                "id": entry_key,
                "title": q_title,
                "description": q_desc,
                "type": q_type,
                "required": is_required,
                "options": options,
                "image": q_img,
                "option_images": opt_images
            }

    return {
        "title": form_title,
        "description": form_description,
        "collects_email": collects_email,
        "header_image": header_image,
        "fields": fields
    }


def inspect_google_form(url: str) -> Dict[str, Any]:
    """Inspect a Google Form by URL (supports forms.gle, viewform, formResponse, and pre-filled URLs)."""
    # 1. Check if it's a pre-filled URL with explicit entry IDs
    prefilled_data = extract_from_prefilled_url(url)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        # Fetch with redirect following to handle forms.gle / shortlinks
        response = requests.get(url.strip(), headers=headers, timeout=12, allow_redirects=True)
        response.raise_for_status()
        
        # Determine clean canonical URL from final redirected response
        final_url = response.url.split("?")[0]
        if "/formResponse" in final_url:
            canonical_viewform = final_url.replace("/formResponse", "/viewform")
        elif not final_url.endswith("/viewform"):
            canonical_viewform = final_url.rstrip("/") + "/viewform"
        else:
            canonical_viewform = final_url

        html_data = parse_form_html(response.text)
    except Exception as e:
        # If network/fetch fails but we had pre-filled params, return what we have
        clean_url = normalize_form_url(url, follow_redirects=False)
        if prefilled_data["fields"]:
            return {
                "success": True,
                "form_url": clean_url,
                "title": "Google Form (from pre-filled URL)",
                "fields": prefilled_data["fields"],
                "email": prefilled_data["email"],
                "warning": f"Could not fetch full HTML: {e}"
            }
        return {
            "success": False,
            "error": f"Failed to fetch form: {e}",
            "form_url": clean_url
        }

    # Merge pre-filled values if available
    merged_fields = html_data["fields"]
    for key, pinfo in prefilled_data["fields"].items():
        if key in merged_fields:
            merged_fields[key]["prefilled_value"] = pinfo["prefilled_value"]
        else:
            merged_fields[key] = pinfo

    response_url = canonical_viewform.replace("/viewform", "/formResponse")

    return {
        "success": True,
        "form_url": canonical_viewform,
        "response_url": response_url,
        "title": html_data.get("title", "Google Form"),
        "description": html_data.get("description", ""),
        "header_image": html_data.get("header_image"),
        "collects_email": html_data.get("collects_email", False) or bool(prefilled_data.get("email")),
        "prefilled_email": prefilled_data.get("email"),
        "fields": merged_fields
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m src.inspector <GOOGLE_FORM_URL>")
        sys.exit(1)

    target_url = sys.argv[1]
    print(f"Inspecting form: {target_url}\n")
    res = inspect_google_form(target_url)

    if not res.get("success"):
        print(f"[ERROR] {res.get('error')}")
        sys.exit(1)

    print(f"Form Title: {res.get('title')}")
    print(f"Canonical Form URL: {res.get('form_url')}")
    print(f"Response Endpoint: {res.get('response_url')}")
    print(f"Collects Email: {res.get('collects_email')}\n")
    print(f"{'Entry ID':<20} | {'Type':<18} | {'Required':<10} | {'Question Title'}")
    print("-" * 80)
    for eid, info in res.get("fields", {}).items():
        req_str = "Yes" if info.get("required") else "No"
        print(f"{eid:<20} | {info.get('type'):<18} | {req_str:<10} | {info.get('title')}")
        if info.get("options"):
            print(f"   -> Options: {', '.join(info['options'])}")
