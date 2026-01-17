
import os
import sys
import django
import random
import datetime
from django.utils import timezone
from django.conf import settings

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.common")
django.setup()

from taiga.users.models import User
from taiga.projects.models import Project, Membership, ProjectTemplate
from taiga.projects.userstories.models import UserStory, RolePoints
from taiga.projects.milestones.models import Milestone
from taiga.projects.tasks.models import Task
from sampledatahelper.helper import SampleDataHelper

def populate_testing_project():
    sd = SampleDataHelper(seed=12345)
    
    print("Fetching 'Testing' project...")
    try:
        project = Project.objects.get(name="Testing")
    except Project.DoesNotExist:
        print("Project 'Testing' not found. Please create it first or rename an existing one.")
        return

    # Create users
    print("Creating users...")
    users = []
    for i in range(1, 4):
        username = f"user_test_{i}"
        email = f"user_test_{i}@example.com"
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            user = User.objects.create(
                username=username,
                email=email,
                full_name=f"Test User {i}",
                token=sd.hex_chars(10, 10),
            )
            user.set_password("password")
            user.save()
        users.append(user)

    # Add users to project
    print("Adding users to project...")
    role = project.roles.first() # Assign first available role
    for user in users:
        if not Membership.objects.filter(project=project, user=user).exists():
            Membership.objects.create(
                project=project,
                user=user,
                role=role,
                email=user.email
            )

    # Create Sprints (Milestones)
    print("Creating Sprints...")
    sprints = []
    start_date = timezone.now() - datetime.timedelta(days=30)
    for i in range(1, 3):
        end_date = start_date + datetime.timedelta(days=14)
        milestone, created = Milestone.objects.get_or_create(
            project=project,
            name=f"Sprint {i}",
            defaults={
                'owner': project.owner,
                'created_date': start_date,
                'modified_date': start_date,
                'estimated_start': start_date,
                'estimated_finish': end_date,
                'order': 10 * i
            }
        )
        sprints.append(milestone)
        start_date = end_date + datetime.timedelta(days=1)

    # Create User Stories
    print("Creating User Stories...")
    points = project.points.all()
    statuses = project.us_statuses.filter(is_closed=False)
    closed_status = project.us_statuses.filter(is_closed=True).first()

    for i in range(1, 15):
        is_closed = random.choice([True, False, False]) # 1/3 chance of being closed
        status = closed_status if is_closed else random.choice(statuses)
        
        us = UserStory.objects.create(
            project=project,
            subject=f"User Story {i}",
            description=sd.paragraph(),
            owner=project.owner,
            status=status,
            milestone=random.choice(sprints) if i > 3 else None,
            assigned_to=random.choice(users),
            is_closed=is_closed,
            finish_date=timezone.now() if is_closed else None
        )
        
        # Assign points
        for role_points in us.role_points.all():
            role_points.points = random.choice(points)
            role_points.save()
        
        us.save()

        # Create Tasks for US
        print(f"Creating Tasks for US {i}...")
        task_statuses = project.task_statuses.all()
        for j in range(1, random.randint(2, 5)):
             task_is_closed = random.choice([True, False])
             task_status = project.task_statuses.get(slug="closed") if task_is_closed and project.task_statuses.filter(slug="closed").exists() else random.choice(task_statuses)

             task = Task.objects.create(
                project=project,
                user_story=us,
                subject=f"Task {j} for US {i}",
                description=sd.paragraph(),
                owner=project.owner,
                status=task_status,
                assigned_to=random.choice(users),
                milestone=us.milestone
            )
             if task.status.is_closed:
                 task.finished_date = timezone.now()
                 task.save()

    print("Data population complete!")

if __name__ == "__main__":
    populate_testing_project()
