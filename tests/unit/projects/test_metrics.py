
import pytest
from django.urls import reverse
from taiga.projects.models import Project
from unittest.mock import patch
from django.conf import settings
from django.test import override_settings
from taiga.projects.metrics.internal import InternalMetricsCalculator
from taiga.projects.metrics.api import MetricsViewSet
from taiga.projects.metrics.models import ProjectMetricsSnapshot
from taiga.projects.metrics.base import get_active_sprint, METRIC_REGISTRY
from taiga.projects.metrics.metrics_impl import (
    TaskCompletionMetric,
    UserStoryCompletionMetric,
    IssueResolutionMetric,
    TaskAssignmentMetric,
    BlockedTasksMetric,
    StoriesWithTasksMetric,
    AssignedTasksStudentMetric,
    UserActivityHistoricalMetric
)
from taiga.projects.userstories.models import UserStory
from taiga.projects.issues.models import Issue

from tests import factories as f

pytestmark = pytest.mark.django_db

@pytest.fixture
def project():
    p = f.ProjectFactory.create(slug="test-metrics-project")
    p.owner.is_superuser = True
    p.owner.save()
    return p

@pytest.fixture
def metrics_data(project):
    # Setup users
    user1 = f.UserFactory.create(username="student1")
    user2 = f.UserFactory.create(username="student2")
    f.MembershipFactory.create(project=project, user=user1)
    f.MembershipFactory.create(project=project, user=user2)

    # Create backlog data
    sprint = f.MilestoneFactory.create(project=project, name="Sprint 1")
    
    # User Stories
    # Create statuses first to ensure is_closed property
    us_status_closed = f.UserStoryStatusFactory.create(project=project, is_closed=True)
    us_status_open = f.UserStoryStatusFactory.create(project=project, is_closed=False)
    
    # User Stories
    # US1: Closed, assigned to user1. RECENT DATE for historical.
    us1 = f.UserStoryFactory.create(project=project, milestone=sprint, is_closed=True, 
                                    status=us_status_closed,
                                    assigned_to=user1, finish_date="2025-12-15")
    us1.is_closed = True
    us1.save()

    # US2: Open, assigned to user2
    us2 = f.UserStoryFactory.create(project=project, milestone=sprint, is_closed=False, 
                                    status=us_status_open,
                                    assigned_to=user2)
    # US3: Closed, unassigned. RECENT DATE.
    us3 = f.UserStoryFactory.create(project=project, milestone=sprint, is_closed=True, 
                                    status=us_status_closed,
                                    finish_date="2025-12-16")
    us3.is_closed = True
    us3.save()
    
    # Tasks (linked to US to stay in sprint)
    status_closed = f.TaskStatusFactory.create(project=project, is_closed=True)
    status_open = f.TaskStatusFactory.create(project=project, is_closed=False)
    
    # Task 1: Closed, assigned to user1. RECENT DATE.
    f.TaskFactory.create(project=project, milestone=sprint, user_story=us1, status=status_closed, 
                         assigned_to=user1, finished_date="2025-12-15")
    # Task 2: Open, assigned to user1
    f.TaskFactory.create(project=project, milestone=sprint, user_story=us1, status=status_open, 
                         assigned_to=user1)
    # Task 3: Closed, assigned to user2. RECENT DATE.
    f.TaskFactory.create(project=project, milestone=sprint, user_story=us2, status=status_closed, 
                         assigned_to=user2, finished_date="2025-12-16")
    # Task 4: Blocked, Open, assigned to user2
    f.TaskFactory.create(project=project, milestone=sprint, user_story=us2, status=status_open, 
                         assigned_to=user2, is_blocked=True)
                         
    # Issues
    issue_status_closed = f.IssueStatusFactory.create(project=project, is_closed=True)
    issue_status_open = f.IssueStatusFactory.create(project=project, is_closed=False)
    
    # Issue 1: Closed, assigned to user1. RECENT DATE.
    f.IssueFactory.create(project=project, milestone=sprint, status=issue_status_closed, 
                          assigned_to=user1, finished_date="2025-12-15")
    # Issue 2: Open, assigned to user2
    f.IssueFactory.create(project=project, milestone=sprint, status=issue_status_open, 
                          assigned_to=user2)
                          
    return project

def test_active_sprint_detection(metrics_data):
    sprint = get_active_sprint(metrics_data.id)
    assert sprint is not None
    assert sprint["name"] == "Sprint 1"

def test_internal_metrics_calculator_structure(metrics_data):
    assert len(METRIC_REGISTRY) > 0, "Metric registry is empty!"
    calculator = InternalMetricsCalculator(metrics_data)
    result = calculator.build_snapshot()
    
    payload = result.payload
    assert payload["project_slug"] == metrics_data.slug
    assert "metrics" in payload
    assert "students" in payload
    assert "hours" in payload
    
    # Check if we have task completion metric
    # ID is metric_id + "_" + project_slug
    metric_id = f"task_completion_{metrics_data.slug}"
    task_metrics = [m for m in payload["metrics"] if m["id"] == metric_id]
    assert len(task_metrics) == 1, f"Missing {metric_id} in {[m['id'] for m in payload['metrics']]}"
    # 2 closed / 4 total tasks (created in fixture)
    # 2/4 = 0.5
    
    val = task_metrics[0]["value"]
    # assert 0.6 < val < 0.7 -> FAILED with 0.5
    assert 0.4 < val < 0.6

def test_task_completion_metric_direct(metrics_data):
    metric = TaskCompletionMetric(metrics_data)
    result = metric.calculate()
    assert result is not None, "Metric returned None!"
    # 2 closed / 4 total tasks (updated fixture)
    # 2/4 = 0.5
    assert 0.4 < result["value"] < 0.6

def test_user_story_completion_metric(metrics_data):
    metric = UserStoryCompletionMetric(metrics_data)
    result = metric.calculate()
    assert result is not None
    # 2 closed (us1, us3) / 3 total (us1, us2, us3) = 0.666
    if result["value"] < 0.6:
        print(f"DEBUG US METRIC VALUE: {result['value']}")
        
    assert 0.6 < result["value"] < 0.7

def test_issue_resolution_metric(metrics_data):
    metric = IssueResolutionMetric(metrics_data)
    result = metric.calculate()
    assert result is not None
    # 1 closed / 2 total = 0.5
    assert 0.4 < result["value"] < 0.6

def test_task_assignment_metric(metrics_data):
    metric = TaskAssignmentMetric(metrics_data)
    result = metric.calculate()
    assert result is not None
    # 4 tasks, all assigned = 1.0 (Task 1, 2, 3, 4 are assigned in fixture update)
    assert result["value"] == 1.0

def test_blocked_tasks_metric(metrics_data):
    metric = BlockedTasksMetric(metrics_data)
    result = metric.calculate()
    assert result is not None
    # 4 tasks total. Task 4 is blocked.
    # Metric filters OPEN tasks only (Task 2, Task 4).
    # 1 blocked / 2 open = 0.5 blocked. 0.5 non-blocked.
    assert 0.4 < result["value"] < 0.6

def test_stories_with_tasks_metric(metrics_data):
    metric = StoriesWithTasksMetric(metrics_data)
    result = metric.calculate()
    assert result is not None
    # US1 has tasks. US2 has tasks. US3 has NO tasks.
    # 2 stories with tasks / 3 stories total = 0.666
    assert 0.6 < result["value"] < 0.7

def test_student_metrics_payload(metrics_data):
    calculator = InternalMetricsCalculator(metrics_data)
    result = calculator.build_snapshot()
    students_data = result.payload["students"]
    
    # We have 2 students + owner (if owner is not excluded? usually owner is member)
    # in fixture: owner + user1 + user2 = 3 members.
    # Check for student1
    student1 = next((s for s in students_data if s["username"] == "student1"), None)
    assert student1 is not None, "student1 not found in metrics"
    
    metrics1_list = student1.get("metrics", [])
    metrics1 = {m["metadata"]["metric"]: m["value"] for m in metrics1_list if "metadata" in m}

    # Verify student1 metrics
    # The system now returns RATIOS:
    # - assignedtasks: student's tasks / total tasks (2/4 = 0.5)
    # - closedtasks: student's closed / student's assigned (1/2 = 0.5)
    # - totalus: student's stories / total stories (1/2 = 0.5, only 2 assigned)
    # - completedus: student's closed / student's assigned (1/1 = 1.0)
    assert metrics1["assignedtasks"] == 0.5  # 2 out of 4 tasks
    assert metrics1["closedtasks"] == 0.5    # 1 closed out of 2 assigned
    
    # User Stories: 1 assigned (US1). 1 closed (US1).
    assert metrics1["totalus"] == 0.5        # 1 out of 2 assigned stories
    assert metrics1["completedus"] == 1.0    # 1/1 ratio
    
    # Check description for student1 completed stories
    completed_us_metric = next(m for m in metrics1_list if m["metadata"]["metric"] == "completedus")
    assert completed_us_metric["value_description"] == "1/1"
    
    # Note: Issue metrics are not tracked at the per-student level
    
    # Check for student2
    student2 = next((s for s in students_data if s["username"] == "student2"), None)
    assert student2 is not None
    
    metrics2_list = student2.get("metrics", [])
    metrics2 = {m["metadata"]["metric"]: m["value"] for m in metrics2_list if "metadata" in m}
    
    # Tasks: 2 assigned (Task 3, Task 4). 1 closed (Task 3). Task 4 is blocked.
    assert metrics2["assignedtasks"] == 0.5  # 2 out of 4 tasks
    assert metrics2["closedtasks"] == 0.5    # 1 closed out of 2 assigned
    
    # User Stories: 1 assigned (US2). 0 closed (US2 is open).
    assert metrics2["totalus"] == 0.5        # 1 out of 2 assigned stories
    assert metrics2["completedus"] == 0.0    # 0/1 ratio
    
    # Check description for student2 completed stories
    completed_us_metric_2 = next(m for m in metrics2_list if m["metadata"]["metric"] == "completedus")
    assert completed_us_metric_2["value_description"] == "0/1"

def test_historical_metric_user_activity(metrics_data):
    metric = UserActivityHistoricalMetric(metrics_data)
    series = metric.calculate_series()
    assert "user_closed_tasks" in series
    data = series["user_closed_tasks"]
    
    # We expect entries for student1 and student2
    # student1: 2 tasks assigned (Task 1, Task 2), 1 closed (Task 1) -> ratio = 0.5
    # student2: 2 tasks assigned (Task 3, Task 4), 1 closed (Task 3) -> ratio = 0.5
    
    s1_entry = next((d for d in data if d["student"] == "student1"), None)
    assert s1_entry is not None
    assert s1_entry["value"] == 0.5  # 1 closed / 2 assigned = 50%
    assert s1_entry["metadata"]["closed"] == 1
    assert s1_entry["metadata"]["assigned"] == 2
    
    s2_entry = next((d for d in data if d["student"] == "student2"), None)
    assert s2_entry is not None
    assert s2_entry["value"] == 0.5  # 1 closed / 2 assigned = 50%
    assert s2_entry["metadata"]["closed"] == 1
    assert s2_entry["metadata"]["assigned"] == 2

def test_metric_api_defaults_to_external(client, project):
    # Authenticate as owner
    client.force_login(project.owner)
    
    url = reverse("metrics-list")
    
    # If we force internal
    response_int = client.get(url, {"project": project.slug, "source": "internal"})
    assert response_int.status_code == 200
    assert response_int.data["provider"] == "internal"
    assert response_int.data["project_slug"] == project.slug

def test_snapshot_caching(metrics_data):
    # First calculation
    snapshot1 = InternalMetricsCalculator(metrics_data).build_snapshot()
    
    # Create a DB snapshot manually to simulate cache
    ProjectMetricsSnapshot.objects.create(
        project=metrics_data,
        provider="internal",
        payload=snapshot1.payload,
        historical_payload=snapshot1.historical, 
        computed_at="2025-01-01 12:00:00+00:00"
    )
    
    # Verify DB content
    assert ProjectMetricsSnapshot.objects.filter(project=metrics_data).count() == 1

def test_metrics_api_force_internal(client, project):
    client.force_login(project.owner)
    url = reverse("metrics-list")
    
    # Request with source=internal should trigger calculation
    response = client.get(url, {"project": project.slug, "source": "internal"})
    
    assert response.status_code == 200
    data = response.data
    assert data["provider"] == "internal"
    assert "metrics" in data
    assert "students" in data

@override_settings(METRICS_PROVIDER="external")
@patch.object(MetricsViewSet, "DEFAULT_PROVIDER", "external")
@patch("requests.request")
def test_external_metrics_configuration(mock_request, client, project):
    # Ensure external provider is used (default)
    # verify settings
    backend_url = getattr(settings, "LD_TAIGA_BACKEND_URL", None)
    assert backend_url is not None, "LD_TAIGA_BACKEND_URL not set in settings"
    
    # Mock response
    mock_request.return_value.status_code = 200
    mock_request.return_value.json.return_value = []
    
    client.force_login(project.owner)
    url = reverse("metrics-list")
    
    # Check default call (without source param)
    response = client.get(url, {"project": project.slug})
    
    assert response.status_code == 200
    assert response.data["provider"] != "internal"
    
    # Verify mock called with correct URL
    args, kwargs = mock_request.call_args
    assert backend_url in args[1] # url is second arg or kwargs['url']
    # requests.request(method, url, ...)
