// ==================== Global State ====================
const API_BASE = '/api';
let currentUser = null;
let authToken = null;
let allProjects = [];
let allUsers = [];

// ==================== Helper Functions ====================
function showScreen(screenId) {
    document.querySelectorAll('.auth-container, .dashboard').forEach(el => {
        el.style.display = 'none';
    });
    document.getElementById(screenId).style.display = screenId === 'dashboardScreen' ? 'flex' : 'flex';
}

function showView(viewName) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(viewName + 'View').classList.add('active');
    
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-view="${viewName}"]`)?.classList.add('active');
}

function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 2rem;
        right: 2rem;
        background: ${type === 'success' ? 'var(--success)' : 'var(--danger)'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: var(--radius-sm);
        box-shadow: var(--shadow-lg);
        z-index: 10000;
        animation: slideInRight 0.3s ease;
    `;
    document.body.appendChild(notification);
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

async function apiRequest(endpoint, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (authToken && !options.skipAuth) {
        headers['Authorization'] = `Bearer ${authToken}`;
    }
    
    const response = await fetch(API_BASE + endpoint, {
        ...options,
        headers
    });
    
    const data = await response.json();
    
    if (!response.ok) {
        throw new Error(data.error || 'Request failed');
    }
    
    return data;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return formatDate(dateString);
}

function getStatusBadgeClass(status) {
    const statusMap = {
        'In Progress': 'in-progress',
        'Completed': 'completed',
        'Cancelled': 'cancelled'
    };
    return statusMap[status] || 'default';
}

function getStepStatusBadgeClass(status) {
    const statusMap = {
        'Pending': 'pending',
        'In Progress': 'in-progress',
        'Completed': 'completed',
        'Sent Back': 'sent-back'
    };
    return statusMap[status] || 'default';
}

// ==================== Authentication ====================
document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    
    try {
        const data = await apiRequest('/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
            skipAuth: true
        });
        
        authToken = data.token;
        currentUser = data.user;
        localStorage.setItem('authToken', authToken);
        localStorage.setItem('currentUser', JSON.stringify(currentUser));
        
        initDashboard();
        showScreen('dashboardScreen');
        showNotification('Welcome back!');
    } catch (error) {
        showNotification(error.message, 'error');
    }
});

document.getElementById('registerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const userData = {
        username: document.getElementById('regUsername').value,
        email: document.getElementById('regEmail').value,
        password: document.getElementById('regPassword').value,
        full_name: document.getElementById('regFullName').value
    };
    
    try {
        await apiRequest('/register', {
            method: 'POST',
            body: JSON.stringify(userData),
            skipAuth: true
        });
        
        showNotification('Account created! Please sign in.');
        document.getElementById('showLogin').click();
        document.getElementById('registerForm').reset();
    } catch (error) {
        showNotification(error.message, 'error');
    }
});

document.getElementById('showRegister').addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('registerScreen').style.display = 'flex';
});

document.getElementById('showLogin').addEventListener('click', (e) => {
    e.preventDefault();
    document.getElementById('registerScreen').style.display = 'none';
    document.getElementById('loginScreen').style.display = 'flex';
});

document.getElementById('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    authToken = null;
    currentUser = null;
    showScreen('loginScreen');
    showNotification('Logged out successfully');
});

// ==================== Navigation ====================
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const view = item.dataset.view;
        showView(view);
        
        if (view === 'dashboard') loadDashboardStats();
        if (view === 'projects') loadProjects();
        if (view === 'create') {
            loadUsersForAssignment();
            setupStepBuilder();
        }
        if (view === 'notifications') loadNotifications();
    });
});

// ==================== Dashboard Initialization ====================
async function initDashboard() {
    // Set user info
    document.getElementById('userName').textContent = currentUser.full_name;
    document.getElementById('userRole').textContent = 'Project Manager';
    
    // Load initial data
    await Promise.all([
        loadDashboardStats(),
        loadProjects(),
        loadNotifications()
    ]);
}

async function loadDashboardStats() {
    try {
        const stats = await apiRequest('/dashboard/stats');
        document.getElementById('totalProjects').textContent = stats.total_projects;
        document.getElementById('activeProjects').textContent = stats.active_projects;
        document.getElementById('completedProjects').textContent = stats.completed_projects;
        document.getElementById('pendingTasks').textContent = stats.my_pending_tasks;
        document.getElementById('notifBadge').textContent = stats.unread_notifications;
        
        // Load recent projects for dashboard
        const projects = await apiRequest('/projects');
        allProjects = projects;
        renderRecentProjects(projects.slice(0, 5));
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

function renderRecentProjects(projects) {
    const container = document.getElementById('recentProjectsList');
    
    if (projects.length === 0) {
        container.innerHTML = '<p class="text-muted">No projects yet. Create your first project!</p>';
        return;
    }
    
    container.innerHTML = projects.map(project => `
        <div class="project-card" onclick="openProjectModal(${project.id})">
            <div class="project-header">
                <div>
                    <div class="project-title">${project.project_name}</div>
                    <div class="project-id">Project #${project.id} ${project.owner_id === currentUser.id ? '(Owner)' : ''}</div>
                </div>
                <span class="status-badge ${getStatusBadgeClass(project.status)}">${project.status}</span>
            </div>
            <div class="project-meta">
                <div class="project-meta-item">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                    </svg>
                    Owner: ${project.owner.full_name}
                </div>
                <div class="project-meta-item">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                    </svg>
                    ${project.steps.length} Steps
                </div>
            </div>
        </div>
    `).join('');
}

// ==================== Projects Management ====================
async function loadProjects() {
    try {
        const projects = await apiRequest('/projects');
        allProjects = projects;
        renderProjects(projects);
    } catch (error) {
        console.error('Failed to load projects:', error);
        showNotification('Failed to load projects', 'error');
    }
}

function renderProjects(projects) {
    const container = document.getElementById('projectsList');
    
    if (projects.length === 0) {
        container.innerHTML = '<p class="text-muted">No projects found. Create your first project!</p>';
        return;
    }
    
    container.innerHTML = projects.map(project => {
        const isOwner = project.owner_id === currentUser.id;
        const myStep = project.steps.find(s => s.assigned_user_id === currentUser.id && s.status === 'In Progress');
        
        return `
            <div class="project-card" onclick="openProjectModal(${project.id})">
                <div class="project-header">
                    <div>
                        <div class="project-title">${project.project_name}</div>
                        <div class="project-id">
                            Project #${project.id} 
                            ${isOwner ? '<span style="color: var(--primary);">• You are the owner</span>' : ''}
                            ${myStep ? '<span style="color: var(--warning);">• ACTION REQUIRED</span>' : ''}
                        </div>
                    </div>
                    <span class="status-badge ${getStatusBadgeClass(project.status)}">${project.status}</span>
                </div>
                <div style="margin: 1rem 0; color: var(--text-secondary); font-size: 0.9rem;">
                    ${project.description.substring(0, 150)}${project.description.length > 150 ? '...' : ''}
                </div>
                <div class="project-meta">
                    <div class="project-meta-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                        </svg>
                        Owner: ${project.owner.full_name}
                    </div>
                    <div class="project-meta-item">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                        </svg>
                        ${project.steps.length} Steps • Current: ${project.current_step_number ? 'Step ' + project.current_step_number : 'Completed'}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

document.getElementById('projectFilter').addEventListener('change', (e) => {
    const filter = e.target.value;
    if (filter === 'all') {
        renderProjects(allProjects);
    } else {
        const filtered = allProjects.filter(p => p.status === filter);
        renderProjects(filtered);
    }
});

// ==================== Create Project with Dynamic Steps ====================
let stepCounter = 0;
let steps = [];

function setupStepBuilder() {
    stepCounter = 0;
    steps = [];
    document.getElementById('stepsContainer').innerHTML = '';
    addStep(); // Add first step by default
}

async function loadUsersForAssignment() {
    try {
        allUsers = await apiRequest('/users');
    } catch (error) {
        console.error('Failed to load users:', error);
    }
}

function addStep() {
    stepCounter++;
    const stepNumber = stepCounter;
    
    const stepHtml = `
        <div class="step-builder-item" data-step="${stepNumber}">
            <div class="step-builder-header">
                <div class="step-number-badge">Step ${stepNumber}</div>
                <button type="button" class="btn-remove-step" onclick="removeStep(${stepNumber})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            <div class="form-group">
                <label>Step Name *</label>
                <input type="text" id="stepName${stepNumber}" required placeholder="e.g., Content Review, Video Editing">
            </div>
            <div class="form-group">
                <label>Assign to User *</label>
                <select id="stepUser${stepNumber}" required>
                    <option value="">Select User</option>
                    ${allUsers.map(u => `<option value="${u.id}">${u.full_name} (@${u.username})</option>`).join('')}
                </select>
            </div>
            <div class="form-group">
                <label>Task Description *</label>
                <textarea id="stepTask${stepNumber}" required rows="3" placeholder="Describe what needs to be done in this step..."></textarea>
            </div>
        </div>
    `;
    
    document.getElementById('stepsContainer').insertAdjacentHTML('beforeend', stepHtml);
    steps.push(stepNumber);
}

function removeStep(stepNumber) {
    if (steps.length === 1) {
        showNotification('At least one step is required', 'error');
        return;
    }
    
    document.querySelector(`[data-step="${stepNumber}"]`).remove();
    steps = steps.filter(s => s !== stepNumber);
    
    // Renumber remaining steps
    steps.forEach((num, index) => {
        const stepEl = document.querySelector(`[data-step="${num}"]`);
        if (stepEl) {
            stepEl.querySelector('.step-number-badge').textContent = `Step ${index + 1}`;
        }
    });
}

document.getElementById('addStepBtn').addEventListener('click', addStep);

document.getElementById('createProjectForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const projectData = {
        project_name: document.getElementById('projectName').value,
        description: document.getElementById('projectDescription').value,
        steps: []
    };
    
    // Collect step data (in reverse order since highest number starts first)
    for (let i = 0; i < steps.length; i++) {
        const stepNum = steps.length - i; // Highest number first
        const actualStepId = steps[i];
        
        const stepName = document.getElementById(`stepName${actualStepId}`).value;
        const stepUser = document.getElementById(`stepUser${actualStepId}`).value;
        const stepTask = document.getElementById(`stepTask${actualStepId}`).value;
        
        if (!stepName || !stepUser || !stepTask) {
            showNotification(`Please fill in all fields for Step ${i + 1}`, 'error');
            return;
        }
        
        projectData.steps.push({
            step_number: stepNum,
            step_name: stepName,
            assigned_user_id: parseInt(stepUser),
            task_description: stepTask
        });
    }
    
    try {
        await apiRequest('/projects/create', {
            method: 'POST',
            body: JSON.stringify(projectData)
        });
        
        showNotification('Project created successfully!');
        document.getElementById('createProjectForm').reset();
        setupStepBuilder();
        showView('projects');
        loadProjects();
        loadDashboardStats();
    } catch (error) {
        showNotification(error.message, 'error');
    }
});

// ==================== Project Modal ====================
async function openProjectModal(projectId) {
    const project = allProjects.find(p => p.id === projectId);
    if (!project) {
        // Fetch if not in cache
        try {
            const fetchedProject = await apiRequest(`/projects/${projectId}`);
            allProjects.push(fetchedProject);
            openProjectModal(projectId);
        } catch (error) {
            showNotification('Failed to load project', 'error');
        }
        return;
    }
    
    const isOwner = project.owner_id === currentUser.id;
    const myStep = project.steps.find(s => s.assigned_user_id === currentUser.id && s.status === 'In Progress');
    
    // Load project actions/history
    let actions = [];
    try {
        actions = await apiRequest(`/projects/${projectId}/actions`);
    } catch (error) {
        console.error('Failed to load actions:', error);
    }
    
    // Load project assets
    let assets = [];
    try {
        assets = await apiRequest(`/projects/${projectId}/assets`);
    } catch (error) {
        console.error('Failed to load assets:', error);
    }
    
    document.getElementById('modalProjectName').textContent = project.project_name;
    
    const modalBody = document.getElementById('modalProjectBody');
    modalBody.innerHTML = `
        <div style="display: grid; gap: 2rem;">
            <!-- Project Info -->
            <div>
                <h3 style="font-size: 1.125rem; margin-bottom: 1rem;">Project Details</h3>
                <div style="display: grid; gap: 1rem; background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-md);">
                    <div>
                        <div style="color: var(--text-muted); font-size: 0.875rem;">Status</div>
                        <span class="status-badge ${getStatusBadgeClass(project.status)}">${project.status}</span>
                    </div>
                    <div>
                        <div style="color: var(--text-muted); font-size: 0.875rem;">Owner</div>
                        <div>${project.owner.full_name} ${isOwner ? '(You)' : ''}</div>
                    </div>
                    <div>
                        <div style="color: var(--text-muted); font-size: 0.875rem;">Description</div>
                        <div style="margin-top: 0.5rem;">${project.description}</div>
                    </div>
                    ${isOwner ? `
                        <div style="margin-top: 1rem;">
                            <button class="btn-secondary" onclick="editProject(${project.id})" style="margin-right: 0.5rem;">Edit Project</button>
                            <button class="btn-action danger" onclick="deleteProject(${project.id})">Delete Project</button>
                        </div>
                    ` : ''}
                </div>
            </div>
            
            <!-- Workflow Timeline -->
            <div>
                <h3 style="font-size: 1.125rem; margin-bottom: 1rem;">Workflow Steps (Work flows from highest to lowest)</h3>
                <div class="workflow-timeline">
                    ${project.steps.map(step => `
                        <div class="timeline-item ${step.status === 'In Progress' ? 'active' : ''} ${step.status === 'Completed' ? 'completed' : ''}">
                            <div class="timeline-marker">
                                <div class="timeline-number">${step.step_number}</div>
                            </div>
                            <div class="timeline-content">
                                <div class="timeline-header">
                                    <div>
                                        <div class="timeline-title">${step.step_name}</div>
                                        <div class="timeline-subtitle">Assigned to: ${step.assigned_user.full_name}</div>
                                    </div>
                                    <span class="status-badge ${getStepStatusBadgeClass(step.status)}">${step.status}</span>
                                </div>
                                <div class="timeline-task">${step.task_description}</div>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <!-- Action Buttons for Current User -->
            ${myStep ? `
                <div id="stepActions">
                    <h3 style="font-size: 1.125rem; margin-bottom: 1rem;">Your Actions (Step ${myStep.step_number}: ${myStep.step_name})</h3>
                    <div style="background: var(--bg-secondary); padding: 1.5rem; border-radius: var(--radius-md);">
                        <p style="margin-bottom: 1rem; color: var(--text-secondary);">You are currently responsible for this step. Choose an action:</p>
                        
                        <!-- Upload Files -->
                        <div class="form-group">
                            <label>Upload Files (Optional)</label>
                            <input type="file" id="stepFiles" multiple>
                        </div>
                        
                        <!-- Comments -->
                        <div class="form-group">
                            <label>Comments</label>
                            <textarea id="stepComments" rows="3" placeholder="Add comments about your work..."></textarea>
                        </div>
                        
                        <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                            <button class="btn-action success" onclick="forwardProject(${project.id})">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 0.5rem;">
                                    <line x1="5" y1="12" x2="19" y2="12"></line>
                                    <polyline points="12 5 19 12 12 19"></polyline>
                                </svg>
                                Forward to Next Step
                            </button>
                            <button class="btn-action danger" onclick="sendBackProject(${project.id})">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 0.5rem;">
                                    <line x1="19" y1="12" x2="5" y2="12"></line>
                                    <polyline points="12 19 5 12 12 5"></polyline>
                                </svg>
                                Send Back
                            </button>
                        </div>
                    </div>
                </div>
            ` : ''}
            
            <!-- Assets -->
            ${assets.length > 0 ? `
                <div>
                    <h3 style="font-size: 1.125rem; margin-bottom: 1rem;">Project Files</h3>
                    <div style="display: grid; gap: 0.5rem;">
                        ${assets.map(asset => `
                            <div style="padding: 0.75rem; background: var(--bg-secondary); border-radius: var(--radius-sm); display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div style="font-weight: 600;">${asset.filename}</div>
                                    <div style="color: var(--text-muted); font-size: 0.875rem;">${asset.asset_type} • Uploaded by ${asset.uploaded_by.full_name}</div>
                                </div>
                                <a href="/uploads/${asset.file_path}?token=${authToken}" target="_blank" class="btn-secondary" style="text-decoration: none;">View/Download</a>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
            <!-- Workflow History -->
            <div>
                <h3 style="font-size: 1.125rem; margin-bottom: 1rem;">Activity Log</h3>
                <div style="display: grid; gap: 0.75rem;">
                    ${actions.map(action => `
                        <div style="padding: 1rem; background: var(--bg-secondary); border-radius: var(--radius-sm); border-left: 3px solid var(--primary);">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                                <div style="font-weight: 600;">${action.action.toUpperCase()}</div>
                                <div style="color: var(--text-muted); font-size: 0.875rem;">${formatRelativeTime(action.timestamp)}</div>
                            </div>
                            <div style="color: var(--text-secondary); font-size: 0.875rem;">
                                ${action.user.full_name}
                                ${action.step_number ? `at Step ${action.step_number}` : ''}
                            </div>
                            ${action.comments ? `<div style="margin-top: 0.5rem; color: var(--text-secondary);">${action.comments}</div>` : ''}
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('projectModal').classList.add('active');
}

// Workflow Actions
async function forwardProject(projectId) {
    const comments = document.getElementById('stepComments').value;
    const files = document.getElementById('stepFiles').files;
    
    // Upload files first if any
    if (files.length > 0) {
        const formData = new FormData();
        for (let file of files) {
            formData.append('files[]', file);
        }
        formData.append('asset_type', 'step_output');
        formData.append('metadata_assets', JSON.stringify({ comments }));
        
        try {
            await fetch(API_BASE + `/projects/${projectId}/upload`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${authToken}` },
                body: formData
            });
        } catch (error) {
            showNotification('Failed to upload files', 'error');
            return;
        }
    }
    
    try {
        await apiRequest(`/projects/${projectId}/forward`, {
            method: 'POST',
            body: JSON.stringify({ comments })
        });
        
        showNotification('Project forwarded successfully!');
        closeModal();
        loadProjects();
        loadDashboardStats();
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

async function sendBackProject(projectId) {
    const comments = document.getElementById('stepComments').value;
    
    if (!comments.trim()) {
        showNotification('Comments are required when sending back', 'error');
        return;
    }
    
    try {
        await apiRequest(`/projects/${projectId}/send-back`, {
            method: 'POST',
            body: JSON.stringify({ comments })
        });
        
        showNotification('Project sent back to previous step');
        closeModal();
        loadProjects();
        loadDashboardStats();
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

async function editProject(projectId) {
    showNotification('Edit functionality - coming soon! For now, delete and recreate the project.', 'error');
    // TODO: Implement edit functionality
}

async function deleteProject(projectId) {
    if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) {
        return;
    }
    
    try {
        await apiRequest(`/projects/${projectId}/delete`, {
            method: 'DELETE'
        });
        
        showNotification('Project deleted successfully');
        closeModal();
        loadProjects();
        loadDashboardStats();
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

function closeModal() {
    document.getElementById('projectModal').classList.remove('active');
}

document.querySelector('.modal-close').addEventListener('click', closeModal);
document.getElementById('projectModal').addEventListener('click', (e) => {
    if (e.target.id === 'projectModal') closeModal();
});

// ==================== Notifications ====================
async function loadNotifications() {
    try {
        const notifications = await apiRequest('/notifications');
        renderNotifications(notifications);
    } catch (error) {
        console.error('Failed to load notifications:', error);
    }
}

function renderNotifications(notifications) {
    const container = document.getElementById('notificationsList');
    
    if (notifications.length === 0) {
        container.innerHTML = '<p class="text-muted">No notifications</p>';
        return;
    }
    
    container.innerHTML = notifications.map(notif => `
        <div class="notification-item ${notif.is_read ? '' : 'unread'}" onclick="markNotificationRead(${notif.id})">
            <div class="notification-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                </svg>
            </div>
            <div class="notification-content">
                <div class="notification-message">${notif.message}</div>
                <div class="notification-time">${formatRelativeTime(notif.created_at)}</div>
            </div>
        </div>
    `).join('');
}

async function markNotificationRead(notifId) {
    try {
        await apiRequest(`/notifications/${notifId}/read`, { method: 'PUT' });
        loadNotifications();
        loadDashboardStats();
    } catch (error) {
        console.error('Failed to mark notification read:', error);
    }
}

document.getElementById('markAllRead').addEventListener('click', async () => {
    try {
        const notifications = await apiRequest('/notifications');
        for (let notif of notifications.filter(n => !n.is_read)) {
            await apiRequest(`/notifications/${notif.id}/read`, { method: 'PUT' });
        }
        loadNotifications();
        loadDashboardStats();
        showNotification('All notifications marked as read');
    } catch (error) {
        showNotification('Failed to mark notifications', 'error');
    }
});

// ==================== Auto-login Check ====================
window.addEventListener('DOMContentLoaded', () => {
    const savedToken = localStorage.getItem('authToken');
    const savedUser = localStorage.getItem('currentUser');
    
    if (savedToken && savedUser) {
        authToken = savedToken;
        currentUser = JSON.parse(savedUser);
        initDashboard();
        showScreen('dashboardScreen');
    }
});