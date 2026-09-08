"""Tests for Form Inspector and URL parser."""
import json
from src.inspector import normalize_form_url, extract_from_prefilled_url, parse_form_html


def test_normalize_form_url():
    url1 = "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/formResponse"
    assert normalize_form_url(url1) == "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform"

    url2 = "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform?usp=sf_link"
    assert normalize_form_url(url2) == "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform"


def test_extract_from_prefilled_url():
    prefill = "https://docs.google.com/forms/d/e/1FAIpQLSeXXXX/viewform?usp=pp_url&entry.123456=John&entry.654321=Option+A&emailAddress=test@example.com"
    data = extract_from_prefilled_url(prefill)
    assert data["email"] == "test@example.com"
    assert "entry.123456" in data["fields"]
    assert data["fields"]["entry.123456"]["prefilled_value"] == "John"
    assert "entry.654321" in data["fields"]
    assert data["fields"]["entry.654321"]["prefilled_value"] == "Option A"


def test_parse_form_html_with_mock():
    mock_fb_data = [
        "Form Description",
        [
            [
                1001,
                "What is your name?",
                "Please enter full name",
                0,
                [[99887766, None, 1]]
            ],
            [
                1002,
                "Choose an option",
                "",
                2,
                [[11223344, [["Alpha"], ["Beta"]], 0]]
            ]
        ]
    ]

    mock_html = f"""
    <html>
      <head><meta property="og:title" content="Sample Registration Form"></head>
      <body>
        <script>
          var FB_PUBLIC_LOAD_DATA_ = {json.dumps(mock_fb_data)};
        </script>
      </body>
    </html>
    """

    res = parse_form_html(mock_html)
    assert res["title"] == "Sample Registration Form"
    assert "entry.99887766" in res["fields"]
    assert res["fields"]["entry.99887766"]["title"] == "What is your name?"
    assert res["fields"]["entry.99887766"]["required"] is True
    assert res["fields"]["entry.99887766"]["type"] == "Short answer"

    assert "entry.11223344" in res["fields"]
    assert res["fields"]["entry.11223344"]["options"] == ["Alpha", "Beta"]
    assert res["fields"]["entry.11223344"]["type"] == "Multiple choice"


def test_parse_form_html_with_images():
    mock_fb_data = [
        "Image Survey Form",
        [
            [
                2001,
                "Who is this player?",
                "",
                2,
                [[55667788, [["Messi"], ["Ronaldo"]], 0]]
            ]
        ]
    ]

    mock_html = f"""
    <html>
      <head><meta property="og:title" content="Football Quiz"></head>
      <body>
        <div style="background-image: url('https://docs.google.com/forms-images-rt/header-banner.png');"></div>
        <div role="listitem">
          <div role="heading">Who is this player?</div>
          <div role="radio">
            <span>Messi</span>
            <img src="https://docs.google.com/forms-images-rt/messi_thumb.png">
          </div>
          <div role="radio">
            <span>Ronaldo</span>
            <img src="https://docs.google.com/forms-images-rt/ronaldo_thumb.png">
          </div>
        </div>
        <script>
          var FB_PUBLIC_LOAD_DATA_ = {json.dumps(mock_fb_data)};
        </script>
      </body>
    </html>
    """

    res = parse_form_html(mock_html)
    assert res["header_image"] == "https://docs.google.com/forms-images-rt/header-banner.png"
    field = res["fields"]["entry.55667788"]
    assert field["option_images"].get("Messi") == "https://docs.google.com/forms-images-rt/messi_thumb.png"
    assert field["option_images"].get("Ronaldo") == "https://docs.google.com/forms-images-rt/ronaldo_thumb.png"

