def _content_url(base_url: str, content: dict) -> str:
    base = base_url.rstrip('/')
    if base.endswith('/wiki'):
        base = base[:-5]

    links = content.get("_links")
    if isinstance(links, dict):
        webui = links.get("webui")
        if isinstance(webui, str) and webui.strip():
            if webui.startswith("http://") or webui.startswith("https://"):
                return webui
            
            webui_path = webui.lstrip('/')
            # Atlassian Cloud tends to return paths without /wiki/ prefix in their APIs
            if webui_path.startswith("spaces/"):
                return f"{base}/wiki/{webui_path}"
                
            if webui_path.startswith("wiki/"):
                return f"{base}/{webui_path}"

            return f"{base_url.rstrip('/')}/{webui_path}"
    return None

print(_content_url('https://shuvabrata.atlassian.net', {'_links': {'webui': '/spaces/Engineerin/pages/26705923/First+Engineering+Page'}}))
print(_content_url('https://shuvabrata.atlassian.net', {'_links': {'webui': '/wiki/spaces/Engineerin/pages/26705923/First+Engineering+Page'}}))
