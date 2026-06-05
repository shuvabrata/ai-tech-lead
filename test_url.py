def _space_url(base_url: str, space: dict) -> str:
    key = space.get("key")
    links = space.get("_links")
    
    if isinstance(links, dict):
        webui = links.get("webui")
        if isinstance(webui, str) and webui.strip():
            if webui.startswith("http://") or webui.startswith("https://"):
                return webui
            
            webui_path = webui.lstrip('/')
            if webui_path.startswith("spaces/"):
                parts = [p for p in webui_path.split('/') if p]
                if len(parts) >= 2:
                    space_key = parts[1]
                    return f"{base_url.rstrip('/')}/wiki/spaces/{space_key}/overview"

            return f"{base_url.rstrip('/')}/{webui_path}"
    
    if key:
        return f"{base_url.rstrip('/')}/wiki/spaces/{key}/overview"

    return None

print(_space_url('https://site.atlassian.net', {'_links': {'webui': '/spaces/Engineerin'}, 'key': 'ENGINEERIN'}))
print(_space_url('https://site.atlassian.net', {'_links': {'webui': 'spaces/ENG'}, 'key': 'ENG'}))
print(_space_url('https://site.atlassian.net', {'_links': {'webui': '/wiki/spaces/ENG/overview'}, 'key': 'ENG'}))
print(_space_url('https://site.atlassian.net', {'key': 'NO_WEBUI'}))
print(_space_url('https://site.atlassian.net', {'_links': {'webui': '/spaces/'}, 'key': 'NO_KEY'}))
