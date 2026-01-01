import os
import sys
import django

# Setup Django environment
sys.path.append('/taiga-back')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.common")
django.setup()

from taiga.projects.metrics import internal
print(f"DEBUG: taiga.projects.metrics.internal file: {internal.__file__}")

from taiga.projects.models import Project
from taiga.projects.metrics.base import get_active_sprint
from taiga.projects.metrics.internal import InternalMetricsCalculator
from taiga.projects.metrics.models import ProjectMetricsSnapshot
from django.db import connection

def debug_metrics(slug):
    try:
        project = Project.objects.get(slug=slug)
        print(f"Project found: {project.name} (ID: {project.id})")
    except Project.DoesNotExist:
        print(f"Project '{slug}' not found.")
        print("Available projects:")
        for p in Project.objects.all():
            print(f" - {p.name} (slug: {p.slug})")
        return

    # Helper function needed 
    def _dictfetchall(cursor): 
        columns = [col[0] for col in cursor.description] 
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    print("\n--- 2.5 MANUAL QUERY VERIFICATION (FULL) ---")
    sql_manual = """
                SELECT
                    u.id AS user_id,
                    u.username,
                    COALESCE(NULLIF(u.full_name, ''), u.username) AS full_name,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id) AS assigned_tasks,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id AND ts.is_closed) AS closed_tasks,
                    COUNT(DISTINCT t.id) FILTER (WHERE t.assigned_to_id = u.id AND t.is_blocked) AS blocked_tasks,
                    COUNT(DISTINCT us.id) FILTER (WHERE us.assigned_to_id = u.id) AS assigned_stories,
                    COUNT(DISTINCT us.id) FILTER (WHERE us.assigned_to_id = u.id AND usst.is_closed) AS closed_stories,
                    COUNT(DISTINCT i.id) FILTER (WHERE i.assigned_to_id = u.id) AS assigned_issues,
                    COUNT(DISTINCT i.id) FILTER (WHERE i.assigned_to_id = u.id AND ist.is_closed) AS closed_issues
                FROM projects_membership m
                JOIN users_user u ON u.id = m.user_id
                LEFT JOIN tasks_task t ON t.project_id = m.project_id AND t.assigned_to_id = u.id
                LEFT JOIN projects_taskstatus ts ON ts.id = t.status_id
                LEFT JOIN userstories_userstory us ON us.project_id = m.project_id AND us.assigned_to_id = u.id
                LEFT JOIN projects_userstorystatus usst ON usst.id = us.status_id
                LEFT JOIN issues_issue i ON i.project_id = m.project_id AND i.assigned_to_id = u.id
                LEFT JOIN projects_issuestatus ist ON ist.id = i.status_id
                WHERE m.project_id = %s AND m.user_id IS NOT NULL
                GROUP BY u.id, u.username, full_name
                ORDER BY full_name ASC
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_manual, [project.id])
        rows = _dictfetchall(cursor)
        print("Manual Query Results:")
        for r in rows:
            print(f"  User {r['username']}: Assigned={r['assigned_stories']}, Closed={r['closed_stories']}")

    print("\n--- 4. FORCE CALCULATION ---")
    calc = InternalMetricsCalculator(project)
    
    # Inspect internal state
    print(f"DEBUG: calc.project.id = {calc.project.id}")
    print(f"DEBUG: calc contents: {dir(calc)}")
    
    s_payload, _ = calc._build_student_metrics()
    
    # Check "Agendados" or similar user if possible
    print("Recalculated Student Metrics (Live):")
    for student in s_payload:
        username = student.get("username")
        metrics = student.get("metrics", [])
        assigned = next((m['value'] for m in metrics if 'totalus' in m['id']), 0)
        closed = next((m['value'] for m in metrics if 'completedus' in m['id']), 0)
        print(f"  - {username}: Assigned={assigned}, Closed={closed}")

if __name__ == "__main__":
    debug_metrics('adriaguilera-agendados') 
