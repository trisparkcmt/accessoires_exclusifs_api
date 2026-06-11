// API Tester Application v2.0 - Dynamic Schema Discovery
class APITester {
    constructor() {
        this.apiUrl = 'http://127.0.0.1:8000/api/v1';
        this.baseUrl = 'http://127.0.0.1:8000';
        this.token = localStorage.getItem('token') || null;
        this.currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
        this.testResults = [];
        this.endpoints = [];
        this.schema = null;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadSchema();
        this.updateUI();
        this.checkServerStatus();
    }

    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchSection(e.target.closest('.nav-btn').dataset.section));
        });

        // API URL
        document.getElementById('btn-check-api').addEventListener('click', () => this.checkServerStatus());

        // Auth
        document.getElementById('login-form').addEventListener('submit', (e) => this.handleLogin(e));
        document.getElementById('btn-logout').addEventListener('click', () => this.logout());

        // Filters
        document.getElementById('endpoint-filter').addEventListener('input', () => this.filterEndpoints());
        document.getElementById('method-filter').addEventListener('change', () => this.filterEndpoints());
        document.getElementById('category-filter').addEventListener('change', () => this.filterEndpoints());

        // Results
        document.getElementById('btn-clear-results').addEventListener('click', () => this.clearResults());
        document.getElementById('btn-export-results').addEventListener('click', () => this.exportResults());

        // Modal
        document.getElementById('modal-close').addEventListener('click', () => this.closeModal());
        document.getElementById('btn-cancel-request').addEventListener('click', () => this.closeModal());
        document.getElementById('btn-send-request').addEventListener('click', () => this.sendRequest());

        // Update API URL
        document.getElementById('api-url').addEventListener('change', (e) => {
            this.apiUrl = e.target.value;
            this.baseUrl = e.target.value.replace('/api/v1', '');
            this.checkServerStatus();
        });
    }

    switchSection(section) {
        // Update nav buttons
        document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelector(`[data-section="${section}"]`).classList.add('active');

        // Update sections
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        document.getElementById(`${section}-section`).classList.add('active');
    }

    async checkServerStatus() {
        try {
            const resp = await fetch(this.apiUrl + '/auth/me/', {
                headers: this.token ? { 'Authorization': `Bearer ${this.token}` } : {}
            });

            if (resp.status === 401 && this.token) {
                this.logout();
            }

            document.getElementById('api-status').textContent = '🟢';
            document.getElementById('server-status').textContent = 'Connecté';
        } catch (e) {
            document.getElementById('api-status').textContent = '🔴';
            document.getElementById('server-status').textContent = 'Déconnecté';
        }
    }

    async handleLogin(e) {
        e.preventDefault();
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;

        await this.login(email, password);
    }

    async login(email, password) {
        try {
            const resp = await fetch(this.apiUrl + '/auth/mobile/login/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            if (!resp.ok) {
                this.showStatus('Identifiants incorrects', 'error');
                return;
            }

            const data = await resp.json();
            this.token = data.access;
            localStorage.setItem('token', this.token);

            // Fetch user profile
            const profileResp = await fetch(this.apiUrl + '/auth/me/', {
                headers: { 'Authorization': `Bearer ${this.token}` }
            });

            const profileData = await profileResp.json();
            this.currentUser = profileData;
            localStorage.setItem('currentUser', JSON.stringify(profileData));

            this.updateUI();
            this.showStatus('Connecté avec succès!', 'success');
            document.getElementById('email').value = '';
            document.getElementById('password').value = '';
        } catch (e) {
            this.showStatus('Erreur de connexion: ' + e.message, 'error');
        }
    }

    quickLogin(email, password) {
        document.getElementById('email').value = email;
        document.getElementById('password').value = password;
        document.getElementById('login-form').dispatchEvent(new Event('submit'));
    }

    logout() {
        this.token = null;
        this.currentUser = null;
        localStorage.removeItem('token');
        localStorage.removeItem('currentUser');
        this.updateUI();
        this.showStatus('Déconnecté', 'success');
    }

    updateUI() {
        const authenticated = !!this.token;

        // Update auth section
        if (authenticated && this.currentUser) {
            document.getElementById('login-form').style.display = 'none';
            document.getElementById('profile-card').style.display = 'block';
            document.getElementById('profile-email').textContent = this.currentUser.email;
            const roles = this.currentUser.roles || [];
            document.getElementById('profile-role').textContent = roles.length > 0 ? roles.join(', ') : 'Client';

            // Sidebar auth info
            document.getElementById('auth-info').style.display = 'block';
            document.getElementById('role-badge').textContent = this.getRole();
            document.getElementById('user-info').textContent = this.currentUser.email;
        } else {
            document.getElementById('login-form').style.display = 'block';
            document.getElementById('profile-card').style.display = 'none';
            document.getElementById('auth-info').style.display = 'none';
        }

        // Update token display
        document.getElementById('jwt-token').value = this.token ? this.token.substring(0, 50) + '...' : 'Pas de token';
    }

    getRole() {
        if (!this.currentUser) return 'Invité';
        const roles = this.currentUser.roles || [];
        if (roles.includes('superadmin')) return '🔑 Superadmin';
        if (roles.includes('serveuse')) return '👩 Serveuse';
        if (roles.includes('prestataire')) return '🏪 Prestataire';
        if (roles.includes('livreur')) return '🛵 Livreur';
        if (roles.includes('client')) return '👤 Client';
        return 'Invité';
    }

    async loadSchema() {
        try {
            // Essayer d'abord le schéma OpenAPI
            const schemaUrl = this.baseUrl + '/api/schema/';
            const resp = await fetch(schemaUrl);

            if (resp.ok) {
                this.schema = await resp.json();
                this.parseOpenAPISchema();
                return;
            }
        } catch (e) {
            console.log('Schema OpenAPI non disponible, utilisation endpoints.json');
        }

        // Fallback sur endpoints.json
        this.loadEndpointsFromJson();
    }

    parseOpenAPISchema() {
        this.endpoints = [];

        // OpenAPI schema structure
        if (!this.schema.paths) {
            this.loadEndpointsFromJson();
            return;
        }

        // Group endpoints by category (first part of path)
        const categories = {};

        Object.entries(this.schema.paths).forEach(([path, methods]) => {
            Object.entries(methods).forEach(([method, details]) => {
                if (method === 'parameters' || method === '$ref') return;

                // Extract category from path
                const pathParts = path.split('/').filter(p => p);
                const category = pathParts[1] || 'general';

                if (!categories[category]) {
                    categories[category] = [];
                }

                // Extract request body schema
                const requestSchema = details.requestBody?.content?.['application/json']?.schema || null;
                const responseSchema = details.responses?.['200']?.content?.['application/json']?.schema || null;

                const endpoint = {
                    method: method.toUpperCase(),
                    path: path.replace(/\{id\}/, '{id}').replace(/\{pk\}/, '{pk}'),
                    name: details.summary || details.operationId || method.toUpperCase() + ' ' + path,
                    category: category,
                    permissions: this.extractPermissions(details),
                    requestSchema: requestSchema,
                    responseSchema: responseSchema,
                    description: details.description || '',
                    parameters: details.parameters || [],
                    tags: details.tags || []
                };

                categories[category].push(endpoint);
                this.endpoints.push(endpoint);
            });
        });

        // Populate category filter
        const categoryFilter = document.getElementById('category-filter');
        categoryFilter.innerHTML = '<option value="">Toutes les catégories</option>';
        Object.keys(categories).sort().forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat;
            categoryFilter.appendChild(opt);
        });

        this.displayEndpoints(this.endpoints);
    }

    extractPermissions(details) {
        // Try to extract permissions from description or tags
        if (details.description && details.description.includes('Permission')) {
            const match = details.description.match(/Permission[s]?:?\s*(\w+)/i);
            if (match) return match[1];
        }
        return 'Mixed';
    }

    loadEndpointsFromJson() {
        // Fallback à endpoints.json
        fetch('./endpoints.json')
            .then(r => r.json())
            .then(data => {
                this.endpoints = [];

                Object.values(data.endpoints).forEach(category => {
                    if (category.endpoints) {
                        this.endpoints.push(...category.endpoints);
                    }
                });

                const categoryFilter = document.getElementById('category-filter');
                categoryFilter.innerHTML = '<option value="">Toutes les catégories</option>';
                const categories = [...new Set(Object.values(data.endpoints).map(c => c.name))];
                categories.forEach(cat => {
                    const opt = document.createElement('option');
                    opt.value = cat;
                    opt.textContent = cat;
                    categoryFilter.appendChild(opt);
                });

                this.displayEndpoints(this.endpoints);
            })
            .catch(e => {
                console.error('Erreur chargement endpoints:', e);
                document.getElementById('endpoints-list').innerHTML =
                    '<p style="color: #ff6b6b;">⚠️ Impossible de charger les endpoints. Vérifiez que le serveur API est en cours d\'exécution.</p>';
            });
    }

    displayEndpoints(endpoints) {
        const container = document.getElementById('endpoints-list');
        container.innerHTML = '';

        if (!endpoints || endpoints.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: #999;">⏳ Chargement des endpoints...</p>';
            return;
        }

        endpoints.forEach(ep => {
            const item = document.createElement('div');
            item.className = 'endpoint-item';
            const endpointJson = JSON.stringify(ep).replace(/"/g, '&quot;');
            item.innerHTML = `
                <div class="endpoint-header">
                    <span class="method-badge method-${ep.method}">${ep.method}</span>
                    <span class="endpoint-path">${ep.path}</span>
                    <span class="endpoint-perms">${ep.permissions || 'Mixed'}</span>
                    <button class="btn btn-sm btn-primary" onclick="app.openEndpointModal('${ep.method}', '${ep.path.replace(/'/g, "\\'")}', '${(ep.permissions || 'Mixed').replace(/"/g, '&quot;')}', ${endpointJson})">Test</button>
                </div>
                <p style="margin-top: 8px; font-size: 0.9em; color: #999;">${ep.name || ep.path}</p>
            `;
            container.appendChild(item);
        });
    }

    filterEndpoints() {
        const search = document.getElementById('endpoint-filter').value.toLowerCase();
        const method = document.getElementById('method-filter').value;
        const category = document.getElementById('category-filter').value;

        const filtered = this.endpoints.filter(ep => {
            const matchSearch = ep.path.toLowerCase().includes(search) || (ep.name && ep.name.toLowerCase().includes(search));
            const matchMethod = !method || ep.method === method;
            const matchCategory = !category || (ep.category || ep.path.split('/')[1]) === category;
            return matchSearch && matchMethod && matchCategory;
        });

        this.displayEndpoints(filtered);
    }

    openEndpointModal(method, path, perms, endpoint) {
        document.getElementById('modal-title').textContent = `Tester: ${method} ${path}`;
        document.getElementById('modal-method').textContent = method;
        document.getElementById('modal-method').className = `method-badge method-${method}`;
        document.getElementById('modal-url').textContent = this.apiUrl + path;
        document.getElementById('modal-perms').textContent = perms;

        // Show/hide request body and display field schema
        const bodySection = document.getElementById('request-body-section');
        if (method === 'GET' || method === 'DELETE') {
            bodySection.style.display = 'none';
        } else {
            bodySection.style.display = 'block';

            // Generate field info if schema exists
            if (endpoint.requestSchema) {
                this.displayFieldSchema(endpoint.requestSchema);
            }

            const exampleBody = endpoint.body || this.generateBodyFromSchema(endpoint.requestSchema);
            document.getElementById('request-body').value = JSON.stringify(exampleBody, null, 2);
        }

        document.getElementById('response-container').style.display = 'none';

        // Store current endpoint data
        this.currentEndpoint = { method, path, endpoint };

        // Open modal
        document.getElementById('request-modal').classList.add('active');
    }

    generateBodyFromSchema(schema) {
        if (!schema || !schema.properties) return {};

        const body = {};
        Object.entries(schema.properties).forEach(([key, def]) => {
            if (def.type === 'string') {
                body[key] = def.example || `exemple_${key}`;
            } else if (def.type === 'integer') {
                body[key] = def.example || 1;
            } else if (def.type === 'number') {
                body[key] = def.example || 0.0;
            } else if (def.type === 'boolean') {
                body[key] = def.example !== undefined ? def.example : true;
            } else if (def.type === 'array') {
                body[key] = [];
            } else if (def.type === 'object') {
                body[key] = {};
            }
        });

        return body;
    }

    displayFieldSchema(schema) {
        const bodySection = document.getElementById('request-body-section');

        // Remove existing schema display if any
        let fieldsContainer = document.getElementById('schema-fields');
        if (fieldsContainer) {
            fieldsContainer.remove();
        }

        fieldsContainer = document.createElement('div');
        fieldsContainer.id = 'schema-fields';
        fieldsContainer.style.marginTop = '12px';
        fieldsContainer.style.padding = '12px';
        fieldsContainer.style.backgroundColor = '#1e1e1e';
        fieldsContainer.style.borderRadius = '4px';
        fieldsContainer.style.maxHeight = '300px';
        fieldsContainer.style.overflowY = 'auto';
        fieldsContainer.style.marginBottom = '12px';

        if (!schema.properties) {
            fieldsContainer.innerHTML = '<p style="color: #888;">Aucun schéma disponible</p>';
            bodySection.insertBefore(fieldsContainer, bodySection.querySelector('.textarea'));
            return;
        }

        const required = schema.required || [];
        let html = '<div style="color: #aaa; font-size: 0.85em; margin-bottom: 8px;"><strong>Champs disponibles:</strong></div>';

        Object.entries(schema.properties).forEach(([fieldName, fieldDef]) => {
            const isRequired = required.includes(fieldName);
            const fieldType = fieldDef.type || 'unknown';
            const fieldDescription = fieldDef.description || '';

            html += `
                <div style="padding: 8px; margin-bottom: 6px; background: #0f1419; border-left: 3px solid ${isRequired ? '#ff6b6b' : '#888'}; border-radius: 3px;">
                    <div style="font-weight: bold; color: #fff; font-size: 0.9em;">
                        ${fieldName}
                        <span style="color: ${isRequired ? '#ff6b6b' : '#888'}; font-size: 0.8em;">
                            (${fieldType}${isRequired ? ', requis' : ', optionnel'})
                        </span>
                    </div>
                    ${fieldDescription ? `<div style="color: #aaa; font-size: 0.8em; margin-top: 4px;">${fieldDescription}</div>` : ''}
                </div>
            `;
        });

        fieldsContainer.innerHTML = html;
        bodySection.insertBefore(fieldsContainer, bodySection.querySelector('.textarea'));
    }

    closeModal() {
        document.getElementById('request-modal').classList.remove('active');
    }

    async sendRequest() {
        if (!this.token && this.currentEndpoint.endpoint.permissions !== 'PUBLIC') {
            this.showStatus('Vous devez être connecté', 'error');
            return;
        }

        const { method, path } = this.currentEndpoint;
        let fullPath = path;

        // Replace path parameters with actual values
        const paramMatch = path.match(/\{(\w+)\}/g);
        if (paramMatch) {
            for (const param of paramMatch) {
                const paramName = param.slice(1, -1);
                const paramValue = prompt(`Entrez la valeur pour ${paramName}:`);
                if (paramValue === null) return; // User cancelled
                fullPath = fullPath.replace(param, paramValue);
            }
        }

        const url = this.apiUrl + fullPath;
        let body = null;

        if (method !== 'GET' && method !== 'DELETE') {
            try {
                body = JSON.parse(document.getElementById('request-body').value);
            } catch (e) {
                this.showStatus('JSON invalide: ' + e.message, 'error');
                return;
            }
        }

        try {
            const opts = {
                method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };

            if (this.token) {
                opts.headers['Authorization'] = `Bearer ${this.token}`;
            }

            if (body) {
                opts.body = JSON.stringify(body);
            }

            const resp = await fetch(url, opts);
            const respText = await resp.text();
            let respData = null;

            try {
                respData = respText ? JSON.parse(respText) : {};
            } catch {
                respData = { raw: respText };
            }

            // Display response
            document.getElementById('response-status').textContent = resp.status;
            document.getElementById('response-status').className = `status-badge ${resp.ok ? 'success' : 'error'}`;
            document.getElementById('response-body').textContent = JSON.stringify(respData, null, 2);
            document.getElementById('response-container').style.display = 'block';

            // Save result
            this.testResults.push({
                method, path: fullPath,
                status: resp.status,
                timestamp: new Date().toISOString(),
                response: respData
            });

            this.updateResultsCount();
        } catch (e) {
            this.showStatus('Erreur: ' + e.message, 'error');
        }
    }

    showStatus(message, type) {
        const container = document.getElementById('login-status');
        container.textContent = message;
        container.className = `status-message ${type}`;
    }

    updateResultsCount() {
        document.getElementById('stat-tests').textContent = this.testResults.length;
    }

    clearResults() {
        if (confirm('Effacer tous les résultats?')) {
            this.testResults = [];
            this.updateResultsCount();
            document.getElementById('results-container').innerHTML = '<p style="text-align: center; color: #999;">Aucun résultat</p>';
        }
    }

    exportResults() {
        const json = JSON.stringify(this.testResults, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `test-results-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
    }
}

// Initialize app
const app = new APITester();

// Load and display roles
document.addEventListener('DOMContentLoaded', () => {
    const rolesList = document.getElementById('roles-list');

    const roles = [
        { badge: 'badge-superadmin', icon: '🔑', name: 'Superadmin', desc: 'Accès complet à tout' },
        { badge: 'badge-serveuse', icon: '👩', name: 'Serveuse', desc: 'Lecture: clients, prestataires, livreurs | Complet: paiements' },
        { badge: 'badge-prestataire', icon: '🏪', name: 'Prestataire', desc: 'Accès au dashboard prestataire' },
        { badge: 'badge-livreur', icon: '🛵', name: 'Livreur', desc: 'Accès au dashboard livreur' },
        { badge: 'badge-client', icon: '👤', name: 'Client', desc: 'Accès catalogue et profil' }
    ];

    roles.forEach(role => {
        const item = document.createElement('div');
        item.className = 'role-item';
        item.innerHTML = `
            <span class="badge ${role.badge}">${role.icon} ${role.name}</span>
            <span class="role-desc">${role.desc}</span>
        `;
        rolesList.appendChild(item);
    });
});
