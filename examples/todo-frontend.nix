# Full-Stack Example: Todo Frontend
#
# A todo app frontend that connects to todo-api.nix backend.
# Edit BACKEND_URL below to match your backend container.

let
  # EDIT THIS: Your backend container URL
  backendUrl = "http://204.168.220.202:9101";
  
  html = pkgs.writeText "index.html" ''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Todo App</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { 
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      padding: 40px 20px;
    }
    .container {
      max-width: 600px;
      margin: 0 auto;
      background: white;
      border-radius: 16px;
      padding: 30px;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }
    h1 { 
      color: #333; 
      margin-bottom: 10px;
      font-size: 2em;
    }
    .subtitle {
      color: #666;
      margin-bottom: 30px;
      font-size: 0.9em;
    }
    .input-group {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
    }
    input[type="text"] {
      flex: 1;
      padding: 12px 16px;
      border: 2px solid #e0e0e0;
      border-radius: 8px;
      font-size: 16px;
      transition: border-color 0.2s;
    }
    input[type="text"]:focus {
      outline: none;
      border-color: #667eea;
    }
    button {
      padding: 12px 24px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      font-size: 16px;
      transition: transform 0.1s, box-shadow 0.2s;
    }
    button:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    button:active {
      transform: translateY(0);
    }
    .todo-list {
      list-style: none;
    }
    .todo-item {
      display: flex;
      align-items: center;
      padding: 16px;
      background: #f8f9fa;
      border-radius: 8px;
      margin-bottom: 10px;
      transition: background 0.2s;
    }
    .todo-item:hover {
      background: #e9ecef;
    }
    .todo-item.done {
      opacity: 0.6;
      text-decoration: line-through;
    }
    .todo-item input[type="checkbox"] {
      margin-right: 12px;
      width: 20px;
      height: 20px;
      cursor: pointer;
    }
    .empty {
      text-align: center;
      color: #666;
      padding: 40px;
      font-style: italic;
    }
    .loading {
      text-align: center;
      padding: 40px;
      color: #667eea;
    }
    .error {
      background: #fee;
      color: #c33;
      padding: 12px;
      border-radius: 8px;
      margin-bottom: 20px;
    }
    .api-info {
      margin-top: 30px;
      padding-top: 20px;
      border-top: 1px solid #e0e0e0;
      font-size: 0.85em;
      color: #666;
    }
    .api-info code {
      background: #f0f0f0;
      padding: 2px 6px;
      border-radius: 4px;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>✅ Todo App</h1>
    <p class="subtitle">Connected to ${backendUrl}</p>
    
    <div id="error" class="error" style="display: none;"></div>
    
    <div class="input-group">
      <input type="text" id="newTodo" placeholder="Add a new todo...">
      <button onclick="addTodo()">Add</button>
    </div>
    
    <ul id="todoList" class="todo-list">
      <li class="loading">Loading todos...</li>
    </ul>
    
    <div class="api-info">
      <p>📡 API: <code>GET ${backendUrl}/todos</code></p>
      <p>🏥 Health: <code>${backendUrl}/health</code></p>
    </div>
  </div>

  <script>
    let todos = [];
    
    async function fetchTodos() {
      const list = document.getElementById('todoList');
      const errorDiv = document.getElementById('error');
      
      try {
        list.innerHTML = '<li class="loading">Loading todos...</li>';
        errorDiv.style.display = 'none';
        
        const response = await fetch('${backendUrl}/todos');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        todos = await response.json();
        renderTodos();
      } catch (err) {
        errorDiv.textContent = 'Failed to load: ' + err.message;
        errorDiv.style.display = 'block';
        list.innerHTML = '<li class="empty">Could not load todos. Is the backend running?</li>';
      }
    }
    
    function renderTodos() {
      const list = document.getElementById('todoList');
      
      if (todos.length === 0) {
        list.innerHTML = '<li class="empty">No todos yet. Add one above!</li>';
        return;
      }
      
      list.innerHTML = todos.map(todo => `
        <li class="todo-item ${todo.done ? 'done' : ''}">
          <input type="checkbox" ${todo.done ? 'checked' : ''} 
                 onchange="toggleTodo(${todo.id})">
          <span>${escapeHtml(todo.text)}</span>
        </li>
      `).join('');
    }
    
    function addTodo() {
      const input = document.getElementById('newTodo');
      const text = input.value.trim();
      
      if (!text) return;
      
      // In a real app, this would POST to the backend
      // For demo, we just add to local list
      const newTodo = {
        id: Date.now(),
        text: text,
        done: false
      };
      todos.push(newTodo);
      input.value = '';
      renderTodos();
    }
    
    function toggleTodo(id) {
      const todo = todos.find(t => t.id === id);
      if (todo) {
        todo.done = !todo.done;
        renderTodos();
      }
    }
    
    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }
    
    // Load todos on page load
    fetchTodos();
  </script>
</body>
</html>
  '';
in
{
  system.activationScripts.createTodoApp = ''
    mkdir -p /var/www
    cp ${html} /var/www/index.html
  '';
  
  services.nginx.enable = true;
  services.nginx.virtualHosts.default = {
    default = true;
    root = "/var/www";
    extraConfig = "charset utf-8; default_type text/html;";
  };
  
  networking.firewall.allowedTCPPorts = [ 80 ];
}
