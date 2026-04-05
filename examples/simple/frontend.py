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
            try {
                // First, discover backend hostname from NCP API
                // Get project name from current hostname (frontend.nix.latha.org -> simple)
                const currentHost = window.location.hostname;
                const projectName = 'simple'; // Could be extracted from hostname or config
                
                // Query NCP API for containers in this project
                const apiUrl = window.location.protocol + '//nix.latha.org/api/v1';
                const containersResp = await fetch(apiUrl + '/containers');
                if (!containersResp.ok) throw new Error('Failed to query NCP API: ' + containersResp.status);
                
                const containers = await containersResp.json();
                // Find backend container (not frontend, with hostname)
                const backend = containers.find(c => c.name !== 'frontend' && c.hostname);
                
                if (!backend || !backend.hostname) {
                    throw new Error('No backend container found with hostname');
                }
                
                dataDiv.innerHTML = '<span class="loading">Found backend at ' + backend.hostname + ', fetching data...</span>';
                
                // Now fetch from discovered backend
                const backendUrl = 'https://' + backend.hostname + '/';
                const response = await fetch(backendUrl);
                if (!response.ok) throw new Error('HTTP ' + response.status);
                const data = await response.json();
                dataDiv.innerHTML = '<span class="success">Backend (' + backend.hostname + ') says:</span> <pre>' + JSON.stringify(data, null, 2) + '</pre>';
            } catch (err) {
                dataDiv.innerHTML = '<span class="error">Error:</span> ' + err.message + 
                                   '<br><small>Make sure backend container is running and has a hostname assigned</small>';
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
