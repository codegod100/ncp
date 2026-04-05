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
    <p>This page fetches data from the backend container via HTTPS at <code>backend.nix.latha.org</code>.</p>
    <div id="data"><span class="loading">Loading from backend...</span></div>
    
    <script>
        async function fetchFromBackend() {
            const dataDiv = document.getElementById('data');
            try {
                // Backend is available at backend.nix.latha.org via Caddy
                const backendUrl = 'https://backend.nix.latha.org/';
                const response = await fetch(backendUrl);
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const data = await response.json();
                dataDiv.innerHTML = '<span class="success">Backend says:</span> <pre>' + JSON.stringify(data, null, 2) + '</pre>';
            } catch (err) {
                dataDiv.innerHTML = '<span class="error">Error fetching from backend:</span> ' + err.message + 
                                   '<br><small>Make sure backend container is running with hostname backend.nix.latha.org</small>';
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
