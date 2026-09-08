"""Single-command launcher for the Auto Google Form Filler Web Dashboard."""
import sys
import webbrowser
import uvicorn


def main():
    port = 8000
    host = "127.0.0.1"
    url = f"http://{host}:{port}"
    
    print("=" * 65)
    print(" 🚀 Auto Google Form Filler - Web Dashboard")
    print(f" 🌐 Running at: {url}")
    print(" 💡 Press CTRL+C in this terminal to stop the server.")
    print("=" * 65)

    try:
        # Open in default browser
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run("src.web.app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
