"""
Automated News Content Production System
A Flask-based application with strict 6-step workflow and RBAC
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
import os
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///news_production.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

CORS(app)
db = SQLAlchemy(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ==================== DATABASE MODELS ====================

class User(db.Model):
    """User model - all users are standard users who can create projects"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'created_at': self.created_at.isoformat(),
            'is_active': self.is_active
        }


class Project(db.Model):
    """Main project model with dynamic workflow"""
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Project creator/owner
    status = db.Column(db.String(50), default='In Progress')  # In Progress, Completed, Cancelled
    current_step_number = db.Column(db.Integer)  # Current active step number
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_projects')
    steps = db.relationship('ProjectStep', backref='project', lazy='dynamic', cascade='all, delete-orphan', order_by='ProjectStep.step_number.desc()')
    
    def to_dict(self, include_steps=True):
        data = {
            'id': self.id,
            'project_name': self.project_name,
            'description': self.description,
            'owner_id': self.owner_id,
            'owner': self.owner.to_dict() if self.owner else None,
            'status': self.status,
            'current_step_number': self.current_step_number,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        if include_steps:
            data['steps'] = [step.to_dict() for step in self.steps.order_by(ProjectStep.step_number.desc()).all()]
        return data


class ProjectStep(db.Model):
    """Dynamic project steps created by owner"""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    step_number = db.Column(db.Integer, nullable=False)  # Higher numbers start first
    step_name = db.Column(db.String(100), nullable=False)  # Custom name
    task_description = db.Column(db.Text, nullable=False)  # Specific task
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(50), default='Pending')  # Pending, In Progress, Completed, Sent Back
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'step_number': self.step_number,
            'step_name': self.step_name,
            'task_description': self.task_description,
            'assigned_user_id': self.assigned_user_id,
            'assigned_user': self.assigned_user.to_dict() if self.assigned_user else None,
            'status': self.status,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'created_at': self.created_at.isoformat()
        }


class WorkflowAction(db.Model):
    """Track all workflow actions for audit trail"""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('project_step.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # forward, send_back, complete, create, edit, delete
    step_number = db.Column(db.Integer)
    comments = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('Project', backref='actions')
    step = db.relationship('ProjectStep', backref='actions')
    user = db.relationship('User')
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'step_id': self.step_id,
            'user': self.user.to_dict() if self.user else None,
            'action': self.action,
            'step_number': self.step_number,
            'comments': self.comments,
            'timestamp': self.timestamp.isoformat()
        }


class ProjectAsset(db.Model):
    """Store project assets (uploaded files, edited content)"""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    asset_type = db.Column(db.String(50), nullable=False)  # raw_footage, edited_content, final_package
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    metadata_assets = db.Column(db.Text)  # JSON metadata_assets
    version = db.Column(db.Integer, default=1)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('Project', backref='assets')
    uploader = db.relationship('User')
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'uploaded_by': self.uploader.to_dict() if self.uploader else None,
            'asset_type': self.asset_type,
            'filename': self.filename,
            'file_path': self.file_path,
            'metadata_assets': json.loads(self.metadata_assets) if self.metadata_assets else None,
            'version': self.version,
            'uploaded_at': self.uploaded_at.isoformat()
        }


class Notification(db.Model):
    """System notifications for users"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User')
    project = db.relationship('Project')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'project_id': self.project_id,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat()
        }


# ==================== AUTHENTICATION DECORATORS ====================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = db.session.get(User, data['user_id'])
            
            if not current_user or not current_user.is_active:
                return jsonify({'error': 'Invalid user'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def project_owner_required(f):
    """Decorator to ensure only project owner can edit/delete"""
    @wraps(f)
    def decorated(current_user, project_id, *args, **kwargs):
        project = db.session.get(Project, project_id)
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        if project.owner_id != current_user.id:
            return jsonify({'error': 'Only project owner can perform this action'}), 403
        
        return f(current_user, project, *args, **kwargs)
    
    return decorated


# ==================== HELPER FUNCTIONS ====================

def create_notification(user_id, project_id, message):
    """Create a notification for a user"""
    notification = Notification(
        user_id=user_id,
        project_id=project_id,
        message=message
    )
    db.session.add(notification)
    db.session.commit()


def log_action(project_id, user_id, action, step_number=None, step_id=None, comments=None):
    """Log a workflow action"""
    workflow_action = WorkflowAction(
        project_id=project_id,
        user_id=user_id,
        action=action,
        step_number=step_number,
        step_id=step_id,
        comments=comments
    )
    db.session.add(workflow_action)
    db.session.commit()


def get_current_step(project):
    """Get the current active step for a project"""
    if not project.current_step_number:
        return None
    return ProjectStep.query.filter_by(
        project_id=project.id,
        step_number=project.current_step_number
    ).first()


def get_next_step(project):
    """Get the next step (lower number) in the workflow"""
    if not project.current_step_number:
        return None
    return ProjectStep.query.filter_by(project_id=project.id).filter(
        ProjectStep.step_number < project.current_step_number
    ).order_by(ProjectStep.step_number.desc()).first()


def get_previous_step(project):
    """Get the previous step (higher number) in the workflow"""
    if not project.current_step_number:
        return None
    return ProjectStep.query.filter_by(project_id=project.id).filter(
        ProjectStep.step_number > project.current_step_number
    ).order_by(ProjectStep.step_number.asc()).first()


# ==================== ROUTES - AUTHENTICATION ====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user - all users are standard users"""
    data = request.get_json()
    
    required_fields = ['username', 'email', 'password', 'full_name']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already exists'}), 400
    
    user = User(
        username=data['username'],
        email=data['email'],
        full_name=data['full_name']
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({
        'message': 'User registered successfully',
        'user': user.to_dict()
    }), 201


@app.route('/api/login', methods=['POST'])
def login():
    """User login"""
    data = request.get_json()
    
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not user.check_password(data['password']) or not user.is_active:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = jwt.encode({
        'user_id': user.id,
        'exp': datetime.now(timezone.utc) + timedelta(days=1)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': user.to_dict()
    }), 200


@app.route('/api/users', methods=['GET'])
@token_required
def get_users(current_user):
    """Get all active users except current user"""
    users = User.query.filter(User.is_active == True, User.id != current_user.id).all()
    return jsonify([user.to_dict() for user in users]), 200


# ==================== ROUTES - WORKFLOW ====================

@app.route('/api/projects/create', methods=['POST'])
@token_required
def create_project(current_user):
    """Create a new project with dynamic steps"""
    data = request.get_json()
    
    required_fields = ['project_name', 'description', 'steps']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if not data['steps'] or len(data['steps']) == 0:
        return jsonify({'error': 'At least one step is required'}), 400
    
    # Validate steps
    for step_data in data['steps']:
        if not all(k in step_data for k in ['step_number', 'step_name', 'task_description', 'assigned_user_id']):
            return jsonify({'error': 'Invalid step data'}), 400
        
        # Check if assigned user exists
        assigned_user = User.query.get(step_data['assigned_user_id'])
        if not assigned_user:
            return jsonify({'error': f'User {step_data["assigned_user_id"]} not found'}), 404
    
    # Create project
    project = Project(
        project_name=data['project_name'],
        description=data['description'],
        owner_id=current_user.id,
        status='In Progress'
    )
    
    db.session.add(project)
    db.session.flush()  # Get project ID
    
    # Create steps
    highest_step = max([s['step_number'] for s in data['steps']])
    
    for step_data in data['steps']:
        step = ProjectStep(
            project_id=project.id,
            step_number=step_data['step_number'],
            step_name=step_data['step_name'],
            task_description=step_data['task_description'],
            assigned_user_id=step_data['assigned_user_id'],
            status='Pending'
        )
        db.session.add(step)
    
    # Set current step to highest number (work starts here)
    project.current_step_number = highest_step
    
    # Mark highest step as In Progress
    highest_step_obj = ProjectStep.query.filter_by(
        project_id=project.id,
        step_number=highest_step
    ).first()
    if highest_step_obj:
        highest_step_obj.status = 'In Progress'
    
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'create', step_number=None, comments='Project created')
    
    # Notify the user assigned to the highest step
    if highest_step_obj:
        create_notification(
            highest_step_obj.assigned_user_id,
            project.id,
            f'New project assigned: {project.project_name}. You are at Step {highest_step}: {highest_step_obj.step_name}'
        )
    
    return jsonify({
        'message': 'Project created successfully',
        'project': project.to_dict()
    }), 201


@app.route('/api/projects/<int:project_id>/edit', methods=['PUT'])
@token_required
@project_owner_required
def edit_project(current_user, project):
    """Edit project details and steps - only owner can edit"""
    data = request.get_json()
    
    # Update basic project info
    if 'project_name' in data:
        project.project_name = data['project_name']
    
    if 'description' in data:
        project.description = data['description']
    
    # Update steps if provided
    if 'steps' in data:
        # Delete existing steps
        ProjectStep.query.filter_by(project_id=project.id).delete()
        
        # Create new steps
        for step_data in data['steps']:
            if not all(k in step_data for k in ['step_number', 'step_name', 'task_description', 'assigned_user_id']):
                return jsonify({'error': 'Invalid step data'}), 400
            
            step = ProjectStep(
                project_id=project.id,
                step_number=step_data['step_number'],
                step_name=step_data['step_name'],
                task_description=step_data['task_description'],
                assigned_user_id=step_data['assigned_user_id'],
                status='Pending'
            )
            db.session.add(step)
        
        # Reset to highest step
        highest_step = max([s['step_number'] for s in data['steps']])
        project.current_step_number = highest_step
    
    project.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'edit', comments='Project edited')
    
    return jsonify({
        'message': 'Project updated successfully',
        'project': project.to_dict()
    }), 200


@app.route('/api/projects/<int:project_id>/delete', methods=['DELETE'])
@token_required
@project_owner_required
def delete_project(current_user, project):
    """Delete project - only owner can delete"""
    project_name = project.project_name
    
    # Delete project (cascade will delete steps, actions, etc.)
    db.session.delete(project)
    db.session.commit()
    
    return jsonify({
        'message': f'Project "{project_name}" deleted successfully'
    }), 200


@app.route('/api/projects/<int:project_id>/forward', methods=['POST'])
@token_required
def forward_step(current_user, project_id):
    """Forward project to next step (lower step number)"""
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Get current step
    current_step = get_current_step(project)
    if not current_step:
        return jsonify({'error': 'No active step found'}), 400
    
    # Verify user is assigned to current step
    if current_step.assigned_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to the current step'}), 403
    
    data = request.get_json() or {}
    comments = data.get('comments', '')
    
    # Mark current step as completed
    current_step.status = 'Completed'
    current_step.completed_at = datetime.utcnow()
    
    # Get next step (lower number)
    next_step = get_next_step(project)
    
    if next_step:
        # Move to next step
        project.current_step_number = next_step.step_number
        next_step.status = 'In Progress'
        
        # Log action
        log_action(
            project.id,
            current_user.id,
            'forward',
            step_number=current_step.step_number,
            step_id=current_step.id,
            comments=comments
        )
        
        # Notify next user
        create_notification(
            next_step.assigned_user_id,
            project.id,
            f'Project forwarded to you: {project.project_name}. Step {next_step.step_number}: {next_step.step_name}'
        )
        
        db.session.commit()
        
        return jsonify({
            'message': f'Project forwarded to Step {next_step.step_number}',
            'project': project.to_dict()
        }), 200
    else:
        # No more steps - project reaches owner (Step 1)
        project.status = 'Completed'
        project.current_step_number = None
        
        # Log action
        log_action(
            project.id,
            current_user.id,
            'complete',
            step_number=current_step.step_number,
            step_id=current_step.id,
            comments=comments
        )
        
        # Notify owner
        create_notification(
            project.owner_id,
            project.id,
            f'Project completed: {project.project_name}. All steps finished.'
        )
        
        db.session.commit()
        
        return jsonify({
            'message': 'Project completed successfully',
            'project': project.to_dict()
        }), 200


@app.route('/api/projects/<int:project_id>/send-back', methods=['POST'])
@token_required
def send_back_step(current_user, project_id):
    """Send project back to previous step (higher step number)"""
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Get current step
    current_step = get_current_step(project)
    if not current_step:
        return jsonify({'error': 'No active step found'}), 400
    
    # Verify user is assigned to current step
    if current_step.assigned_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to the current step'}), 403
    
    data = request.get_json()
    if not data or not data.get('comments'):
        return jsonify({'error': 'Comments are required when sending back'}), 400
    
    comments = data['comments']
    
    # Get previous step (higher number)
    previous_step = get_previous_step(project)
    
    if not previous_step:
        return jsonify({'error': 'No previous step to send back to'}), 400
    
    # Mark current step as sent back
    current_step.status = 'Sent Back'
    
    # Move to previous step
    project.current_step_number = previous_step.step_number
    previous_step.status = 'In Progress'
    previous_step.completed_at = None  # Reset completion
    
    # Log action
    log_action(
        project.id,
        current_user.id,
        'send_back',
        step_number=current_step.step_number,
        step_id=current_step.id,
        comments=comments
    )
    
    # Notify previous user
    create_notification(
        previous_step.assigned_user_id,
        project.id,
        f'Project sent back to you: {project.project_name}. Step {previous_step.step_number}: {previous_step.step_name}. Reason: {comments}'
    )
    
    db.session.commit()
    
    return jsonify({
        'message': f'Project sent back to Step {previous_step.step_number}',
        'project': project.to_dict()
    }), 200
    """Step 1: Manager initiates a project"""
    data = request.get_json()
    
    required_fields = ['project_name', 'instructions', 'deadline', 
                      'step2_user_id', 'step3_user_id', 'step4_user_id', 
                      'step5_user_id', 'step6_user_id']
    
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Validate deadline
    try:
        deadline = datetime.fromisoformat(data['deadline'].replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Invalid deadline format'}), 400
    
    # Validate assigned users exist
    for step in range(2, 7):
        user_id = data[f'step{step}_user_id']
        if not db.session.get(User, user_id):
            return jsonify({'error': f'User for step {step} not found'}), 404
    
    project = Project(
        project_name=data['project_name'],
        instructions=data['instructions'],
        deadline=deadline,
        created_by=current_user.id,
        step2_user_id=data['step2_user_id'],
        step3_user_id=data['step3_user_id'],
        step4_user_id=data['step4_user_id'],
        step5_user_id=data['step5_user_id'],
        step6_user_id=data['step6_user_id'],
        status='Assigned',
        current_step=6
    )
    
    db.session.add(project)
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'initiate', 1, None, 'Assigned')
    
    # Notify Reporter (Step 6)
    create_notification(
        project.step6_user_id,
        project.id,
        f'New project assigned: {project.project_name}. Please upload raw footage.'
    )
    
    return jsonify({
        'message': 'Project initiated successfully',
        'project': project.to_dict()
    }), 201


@app.route('/api/upload-raw', methods=['POST'])
@token_required

def upload_raw(current_user):
    """Step 6: Reporter uploads raw footage"""
    project_id = request.form.get('project_id')
    metadata_assets = request.form.get('metadata_assets', '{}')
    
    if not project_id:
        return jsonify({'error': 'Project ID required'}), 400
    
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if project.step6_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to this project'}), 403
    
    if project.current_step != 6:
        return jsonify({'error': 'Project is not at Step 6'}), 400
    
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files[]')
    uploaded_assets = []
    
    for file in files:
        if file.filename == '':
            continue
        
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{project_id}_{filename}")
        file.save(file_path)
        
        asset = ProjectAsset(
            project_id=project.id,
            uploaded_by=current_user.id,
            asset_type='raw_footage',
            filename=filename,
            file_path=file_path,
            metadata_assets=metadata_assets
        )
        db.session.add(asset)
        uploaded_assets.append(asset)
    
    # Update project status
    old_status = project.status
    project.status = 'In Progress'
    project.current_step = 5
    project.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'upload-raw', 6, old_status, 'In Progress')
    
    # Notify Editor (Step 5)
    create_notification(
        project.step5_user_id,
        project.id,
        f'Raw footage uploaded for project: {project.project_name}. Ready for editing.'
    )
    
    return jsonify({
        'message': 'Raw footage uploaded successfully',
        'project': project.to_dict(),
        'assets': [asset.to_dict() for asset in uploaded_assets]
    }), 200


@app.route('/api/edit-content', methods=['POST'])
@token_required

def edit_content(current_user):
    """Step 5: Editor submits edited content"""
    project_id = request.form.get('project_id')
    comments = request.form.get('comments', '')
    
    if not project_id:
        return jsonify({'error': 'Project ID required'}), 400
    
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if project.step5_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to this project'}), 403
    
    if project.current_step != 5:
        return jsonify({'error': 'Project is not at Step 5'}), 400
    
    if 'files[]' not in request.files:
        return jsonify({'error': 'No edited content uploaded'}), 400
    
    files = request.files.getlist('files[]')
    uploaded_assets = []
    
    for file in files:
        if file.filename == '':
            continue
        
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{project_id}_edited_{filename}")
        file.save(file_path)
        
        asset = ProjectAsset(
            project_id=project.id,
            uploaded_by=current_user.id,
            asset_type='edited_content',
            filename=filename,
            file_path=file_path,
            metadata_assets=json.dumps({'comments': comments})
        )
        db.session.add(asset)
        uploaded_assets.append(asset)
    
    # Update project status
    old_status = project.status
    project.status = 'Submitted'
    project.current_step = 4
    project.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'edit-content', 5, old_status, 'Submitted', comments)
    
    # Notify Checker 01 (Step 4)
    create_notification(
        project.step4_user_id,
        project.id,
        f'Edited content ready for quality verification: {project.project_name}'
    )
    
    return jsonify({
        'message': 'Edited content submitted successfully',
        'project': project.to_dict()
    }), 200


@app.route('/api/verify-quality', methods=['POST'])
@token_required
def verify_quality(current_user):
    """Step 4: Checker 01 verifies quality"""
    data = request.get_json()
    
    if not data.get('project_id'):
        return jsonify({'error': 'Project ID required'}), 400
    
    project = Project.query.get(data['project_id'])
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if project.step4_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to this project'}), 403
    
    if project.current_step != 4:
        return jsonify({'error': 'Project is not at Step 4'}), 400
    
    approved = data.get('approved', False)
    comments = data.get('comments', '')
    
    old_status = project.status
    
    if approved:
        project.status = 'Submitted'
        project.current_step = 3
        project.updated_at = datetime.utcnow()
        
        # Notify Checker 02 (Step 3)
        create_notification(
            project.step3_user_id,
            project.id,
            f'Quality verified for project: {project.project_name}. Ready for policy check.'
        )
        
        message = 'Quality verification passed'
    else:
        # Reject - send back to Editor (Step 5)
        project.current_step = 5
        project.updated_at = datetime.utcnow()
        
        # Notify Editor
        create_notification(
            project.step5_user_id,
            project.id,
            f'Quality issues found in project: {project.project_name}. Comments: {comments}'
        )
        
        message = 'Content rejected, sent back to Editor'
    
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'verify-quality', 4, old_status, project.status, comments)
    
    return jsonify({
        'message': message,
        'project': project.to_dict()
    }), 200


@app.route('/api/verify-policy', methods=['POST'])
@token_required
def verify_policy(current_user):
    """Step 3: Checker 02 verifies policy compliance"""
    data = request.get_json()
    
    if not data.get('project_id'):
        return jsonify({'error': 'Project ID required'}), 400
    
    project = Project.query.get(data['project_id'])
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if project.step3_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to this project'}), 403
    
    if project.current_step != 3:
        return jsonify({'error': 'Project is not at Step 3'}), 400
    
    approved = data.get('approved', False)
    comments = data.get('comments', '')
    
    old_status = project.status
    
    if approved:
        project.status = 'Edited'
        project.current_step = 2
        project.updated_at = datetime.utcnow()
        
        # Notify Automation Layer (Step 2)
        create_notification(
            project.step2_user_id,
            project.id,
            f'Policy verified for project: {project.project_name}. Ready for logging and prep.'
        )
        
        message = 'Policy verification passed'
    else:
        # Reject - send back to Checker 01 (Step 4)
        project.current_step = 4
        project.updated_at = datetime.utcnow()
        
        # Notify Checker 01
        create_notification(
            project.step4_user_id,
            project.id,
            f'Policy issues found in project: {project.project_name}. Comments: {comments}'
        )
        
        message = 'Content rejected, sent back to Checker 01'
    
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'verify-policy', 3, old_status, project.status, comments)
    
    return jsonify({
        'message': message,
        'project': project.to_dict()
    }), 200


@app.route('/api/log-and-prep', methods=['POST'])
@token_required
def log_and_prep(current_user):
    """Step 2: Automation layer logs and prepares final package"""
    data = request.get_json()
    
    if not data.get('project_id'):
        return jsonify({'error': 'Project ID required'}), 400
    
    project = Project.query.get(data['project_id'])
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if project.step2_user_id != current_user.id:
        return jsonify({'error': 'You are not assigned to this project'}), 403
    
    if project.current_step != 2:
        return jsonify({'error': 'Project is not at Step 2'}), 400
    
    comments = data.get('comments', '')
    
    old_status = project.status
    project.status = 'Edited'
    project.current_step = 1
    project.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'log-and-prep', 2, old_status, 'Edited', comments)
    
    # Notify Manager (Step 1)
    create_notification(
        project.created_by,
        project.id,
        f'Final package prepared for project: {project.project_name}. Ready for approval.'
    )
    
    return jsonify({
        'message': 'Package logged and prepared successfully',
        'project': project.to_dict()
    }), 200


@app.route('/api/approve', methods=['POST'])
@token_required
def approve_project(current_user):
    """Step 1: Manager final approval and publishing"""
    data = request.get_json()
    
    if not data.get('project_id'):
        return jsonify({'error': 'Project ID required'}), 400
    
    project = Project.query.get(data['project_id'])
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    if project.created_by != current_user.id:
        return jsonify({'error': 'You are not the project creator'}), 403
    
    if project.current_step != 1:
        return jsonify({'error': 'Project is not ready for approval'}), 400
    
    approved = data.get('approved', False)
    comments = data.get('comments', '')
    platforms = data.get('platforms', ['Facebook', 'YouTube', 'Instagram'])
    
    old_status = project.status
    
    if approved:
        project.status = 'Approved'
        project.current_step = 0  # Workflow complete
        project.updated_at = datetime.utcnow()
        
        # Simulate publishing
        project.status = 'Published'
        
        # Notify all team members
        for step in range(2, 7):
            user_id = getattr(project, f'step{step}_user_id')
            if user_id:
                create_notification(
                    user_id,
                    project.id,
                    f'Project published: {project.project_name} on platforms: {", ".join(platforms)}'
                )
        
        message = f'Project approved and published to: {", ".join(platforms)}'
    else:
        # Reject - send back to Automation (Step 2)
        project.current_step = 2
        project.updated_at = datetime.utcnow()
        
        # Notify Automation
        create_notification(
            project.step2_user_id,
            project.id,
            f'Approval rejected for project: {project.project_name}. Comments: {comments}'
        )
        
        message = 'Project rejected, sent back to Automation Layer'
    
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'approve', 1, old_status, project.status, comments)
    
    return jsonify({
        'message': message,
        'project': project.to_dict()
    }), 200


# ==================== ROUTES - DATA RETRIEVAL ====================

@app.route('/api/projects', methods=['GET'])
@token_required
def get_projects(current_user):
    """Get all projects where user is owner or assigned to a step"""
    # Get projects owned by user
    owned_projects = Project.query.filter_by(owner_id=current_user.id).all()
    
    # Get projects where user is assigned to any step
    assigned_steps = ProjectStep.query.filter_by(assigned_user_id=current_user.id).all()
    assigned_project_ids = [step.project_id for step in assigned_steps]
    assigned_projects = Project.query.filter(Project.id.in_(assigned_project_ids)).all() if assigned_project_ids else []
    
    # Combine and deduplicate
    all_projects = {p.id: p for p in owned_projects + assigned_projects}
    
    return jsonify([p.to_dict() for p in all_projects.values()]), 200


@app.route('/api/projects/<int:project_id>', methods=['GET'])
@token_required
def get_project(current_user, project_id):
    """Get single project details"""
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Check if user has access (owner or assigned to any step)
    is_owner = project.owner_id == current_user.id
    is_assigned = ProjectStep.query.filter_by(
        project_id=project_id,
        assigned_user_id=current_user.id
    ).first() is not None
    
    if not (is_owner or is_assigned):
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify(project.to_dict()), 200


@app.route('/api/projects/<int:project_id>/actions', methods=['GET'])
@token_required
def get_project_actions(current_user, project_id):
    """Get workflow actions (audit trail) for a project"""
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    actions = WorkflowAction.query.filter_by(project_id=project_id).order_by(WorkflowAction.timestamp.desc()).all()
    return jsonify([action.to_dict() for action in actions]), 200


@app.route('/api/projects/<int:project_id>/assets', methods=['GET'])
@token_required
def get_project_assets(current_user, project_id):
    """Get all assets for a project"""
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    assets = ProjectAsset.query.filter_by(project_id=project_id).order_by(ProjectAsset.uploaded_at.desc()).all()
    return jsonify([asset.to_dict() for asset in assets]), 200


@app.route('/api/notifications', methods=['GET'])
@token_required
def get_notifications(current_user):
    """Get user notifications"""
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([notif.to_dict() for notif in notifications]), 200


@app.route('/api/notifications/<int:notif_id>/read', methods=['PUT'])
@token_required
def mark_notification_read(current_user, notif_id):
    """Mark notification as read"""
    notification = Notification.query.get(notif_id)
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'message': 'Notification marked as read'}), 200


@app.route('/api/dashboard/stats', methods=['GET'])
@token_required
def get_dashboard_stats(current_user):
    """Get dashboard statistics"""
    # Projects owned by user
    owned_projects = Project.query.filter_by(owner_id=current_user.id).count()
    
    # Projects where user is assigned
    assigned_steps = ProjectStep.query.filter_by(assigned_user_id=current_user.id).all()
    assigned_project_ids = [step.project_id for step in assigned_steps]
    assigned_projects_count = len(set(assigned_project_ids))
    
    total_projects = owned_projects + assigned_projects_count
    
    # Active projects (In Progress status)
    active_owned = Project.query.filter_by(owner_id=current_user.id, status='In Progress').count()
    active_assigned = Project.query.filter(
        Project.id.in_(assigned_project_ids),
        Project.status == 'In Progress'
    ).count() if assigned_project_ids else 0
    active_projects = active_owned + active_assigned
    
    # Completed projects
    completed_owned = Project.query.filter_by(owner_id=current_user.id, status='Completed').count()
    completed_assigned = Project.query.filter(
        Project.id.in_(assigned_project_ids),
        Project.status == 'Completed'
    ).count() if assigned_project_ids else 0
    completed_projects = completed_owned + completed_assigned
    
    # My pending tasks (steps assigned to me that are In Progress)
    my_pending_tasks = ProjectStep.query.filter_by(
        assigned_user_id=current_user.id,
        status='In Progress'
    ).count()
    
    unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    
    return jsonify({
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'my_pending_tasks': my_pending_tasks,
        'unread_notifications': unread_notifications
    }), 200


# ==================== FILE UPLOAD & DOWNLOAD ====================

@app.route('/api/projects/<int:project_id>/upload', methods=['POST'])
@token_required
def upload_files(current_user, project_id):
    """Upload files for a project step"""
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404
    
    # Check if user has access
    is_owner = project.owner_id == current_user.id
    is_assigned = ProjectStep.query.filter_by(
        project_id=project_id,
        assigned_user_id=current_user.id
    ).first() is not None
    
    if not (is_owner or is_assigned):
        return jsonify({'error': 'Access denied'}), 403
    
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files[]')
    asset_type = request.form.get('asset_type', 'general')
    metadata_assets = request.form.get('metadata_assets', '{}')
    
    uploaded_assets = []
    
    for file in files:
        if file.filename == '':
            continue
        
        filename = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{project_id}_{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        asset = ProjectAsset(
            project_id=project.id,
            uploaded_by=current_user.id,
            asset_type=asset_type,
            filename=filename,
            file_path=unique_filename,  # Store only filename, not full path
            metadata_assets=metadata_assets
        )
        db.session.add(asset)
        uploaded_assets.append(asset)
    
    db.session.commit()
    
    # Log action
    log_action(project.id, current_user.id, 'upload', comments=f'Uploaded {len(uploaded_assets)} file(s)')
    
    return jsonify({
        'message': f'{len(uploaded_assets)} file(s) uploaded successfully',
        'assets': [asset.to_dict() for asset in uploaded_assets]
    }), 200


@app.route('/uploads/<path:filename>', methods=['GET'])
def download_file(filename):
    """Download uploaded file - accepts token via query parameter or header"""
    # Try to get token from query parameter first, then header
    token = request.args.get('token') or request.headers.get('Authorization')
    
    if not token:
        return jsonify({'error': 'Token is missing'}), 401
    
    try:
        if token.startswith('Bearer '):
            token = token[7:]
        
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        current_user = db.session.get(User, data['user_id'])
        
        if not current_user or not current_user.is_active:
            return jsonify({'error': 'Invalid user'}), 401
        
        # Verify user has access to this file
        asset = ProjectAsset.query.filter_by(file_path=filename).first()
        if not asset:
            return jsonify({'error': 'File not found'}), 404
        
        project = Project.query.get(asset.project_id)
        if not project:
            return jsonify({'error': 'Project not found'}), 404
        
        # Check access
        is_owner = project.owner_id == current_user.id
        is_assigned = ProjectStep.query.filter_by(
            project_id=project.id,
            assigned_user_id=current_user.id
        ).first() is not None
        
        if not (is_owner or is_assigned):
            return jsonify({'error': 'Access denied'}), 403
        
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
        
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== INITIALIZE DATABASE ====================

def init_db():
    """Initialize database with sample data"""
    with app.app_context():
        db.create_all()
        
        # Check if users exist
        if User.query.count() == 0:
            # Create sample users - all standard users
            users_data = [
                {'username': 'alice', 'email': 'alice@example.com', 'password': 'password123', 'full_name': 'Alice Johnson'},
                {'username': 'bob', 'email': 'bob@example.com', 'password': 'password123', 'full_name': 'Bob Smith'},
                {'username': 'charlie', 'email': 'charlie@example.com', 'password': 'password123', 'full_name': 'Charlie Davis'},
                {'username': 'diana', 'email': 'diana@example.com', 'password': 'password123', 'full_name': 'Diana Wilson'},
                {'username': 'emma', 'email': 'emma@example.com', 'password': 'password123', 'full_name': 'Emma Martinez'},
            ]
            
            for user_data in users_data:
                user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    full_name=user_data['full_name']
                )
                user.set_password(user_data['password'])
                db.session.add(user)
            
            db.session.commit()
            print("Sample users created!")
            print("All users can create and manage projects")
            print("Login credentials (password: password123):")
            print("  - alice, bob, charlie, diana, emma")


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)