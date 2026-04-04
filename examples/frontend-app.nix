# Frontend App Container
#
# A frontend that fetches data from a backend container.
# Edit BACKEND_URL below to point to your backend.

let
  # EDIT THIS: URL to your backend container
  backendUrl = "http://204.168.220.202:9101/";  # Change to your backend IP:port
  
  # HTML content with JavaScript fetch
  htmlContent = pkgs.writeText "index.html" ''
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Frontend App</title>
  <style>
    body { 
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 800px; 
      margin: 40px auto; 
      padding: 20px;
      background: #f5f5f5;
    }
    .box {
      background: white;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 { color: #333; border-bottom: 3px solid #007acc; padding-bottom: 10px; }
    pre {
      background: #1e1e1e;
      color: #0f0;
      padding: 15px;
      border-radius: 4px;
      overflow-x: auto;
    }
    button {
      padding: 10px 20px;
      background: #007acc;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      margin: 5px;
    }
    button:hover { background: #005fa3; }
    .status { color: #666; font-style: italic; }
  </style>
</head>
<body>
  <h1>🚀 Frontend App</h1>
  
  <div class="box">
    <h3>Backend Connection</h3>
    <p class="status">Backend URL: ${backendUrl}</p>
    
    <button onclick="fetchData()">Fetch from Backend</button>
    <button onclick="clearData()">Clear</button>
    
    <h4>Response:</h4>
    <pre id="output">Click button to fetch data...</pre>
  </div>
  
  <p><a href="${backendUrl}" target="_blank">Open Backend Directly</a></p>

  <script>
    async function fetchData() {
      const output = document.getElementById("output");
      output.textContent = "Loading...";
      
      try {
        const response = await fetch("${backendUrl}");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        output.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        output.textContent = "Error: " + error.message;
        console.error("Fetch error:", error);
      }
    }
    
    function clearData() {
      document.getElementById("output").textContent = "Click button to fetch data...";
    }
  </script>
</body>
</html>
  '';
in
{
  # Create the HTML file at boot
  system.activationScripts.createFrontend = ''
    mkdir -p /var/www
    cp ${htmlContent} /var/www/index.html
  '';

  # Enable nginx to serve the files
  services.nginx.enable = true;
  services.nginx.virtualHosts.default = {
    default = true;
    root = "/var/www";
    extraConfig = "charset utf-8; default_type text/html;";
  };

  # Allow HTTP traffic
  networking.firewall.allowedTCPPorts = [ 80 ];
}
