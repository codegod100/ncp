from http.server import BaseHTTPRequestHandler, HTTPServer

HTML_CONTENT = b"""<!DOCTYPE html>
<html>
<head>
    <title>Frontend</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 600px; margin: 2rem auto; padding: 1rem; }
        h1 { color: #333; border-bottom: 2px solid #5277c3; padding-bottom: 0.5rem; }
        #data { background: #f5f5f5; padding: 1rem; border-radius: 8px; margin-top: 1rem; }
        .loading { color: #666; }
        .error { color: #d32f2f; }
        .success { color: #388e3c; }
    </style>
</head>
<body>
    <h1>Hello from Frontend</h1>
    <p>This page fetches data from the backend container via HTTPS (discovered via NCP API).</p>
    <div id="data"><span class="loading">Discovering backend...</span></div>
    
    <script>
        async function fetchFromBackend() {
            const dataDiv = document.getElementById('data');
            
            // Try multiple strategies to find backend
            let backendUrl = null;
            let backendHostname = null;
            
            // Strategy 1: Try NCP discovery API (public, no auth needed)
            try {
                const apiUrl = window.location.protocol + '//nix.latha.org/api/v1';
                // Extract project from current hostname (e.g., simple-frontend -> simple)
                const hostname = window.location.hostname;
                const projectMatch = hostname.match(/^([a-z]+)-/);
                const project = projectMatch ? projectMatch[1] : 'simple';
                
                const discoverResp = await fetch(apiUrl + '/discover/' + project + '/backend');
                if (discoverResp.ok) {
                    const info = await discoverResp.json();
                    if (info.hostname) {
                        backendHostname = info.hostname;
                        backendUrl = info.url;
                    }
                }
            } catch (e) {
                console.log('NCP discovery failed:', e);
            }
            
            // Strategy 2: Fall back to port-based URL (HTTP, not HTTPS since ports are plain HTTP)
            if (!backendUrl) {
                backendUrl = 'http://nix.latha.org:9001/';
                backendHostname = 'nix.latha.org:9001';
                dataDiv.innerHTML = '<span class="loading">API discovery failed, trying port fallback...</span>';
            }
            
            // Fetch from backend
            try {
                dataDiv.innerHTML = '<span class="loading">Fetching from ' + backendHostname + '...</span>';
                const response = await fetch(backendUrl);
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const data = await response.json();
                dataDiv.innerHTML = '<span class="success">Backend (' + backendHostname + ') says:</span> <pre>' + JSON.stringify(data, null, 2) + '</pre>';
            } catch (err) {
                dataDiv.innerHTML = '<span class="error">Error fetching from backend:</span> ' + err.message + 
                                   '<br><small>Backend URL tried: ' + backendUrl + '</small>';
            }
        }
        
        fetchFromBackend();
    </script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(HTML_CONTENT)
    
    def log_message(self, *args): 
        pass

HTTPServer(("", 80), Handler).serve_forever()
