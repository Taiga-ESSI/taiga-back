# Informe de cambios: roles UX, Design, Wiki, Epics.

## Objetivo
Ajustar la configuración inicial de los proyectos para que los roles **UX** y **Design** aparezcan con el toggle `help_role_enabled` deshabilitado al crear un nuevo proyecto. También hemos activado por defecto las épicas y desactivado la wiki en nuevos proyectos.

## Modificaciones realizadas
- Actualización de `taiga/projects/fixtures/initial_project_templates.json` para establecer `"computable": false` en los roles `ux` y `design` de los dos templates iniciales y ajustar `"is_epics_activated": true` y `"is_wiki_activated": false`.
- Migración de datos `taiga/projects/migrations/0068_update_roles_computable.py` para aplicar automáticamente el cambio en las plantillas ya almacenadas en la base de datos.
- La propiedad `computable` controla el estado del toggle `help_role_enabled` en la interfaz de administración de roles.

## Impacto esperado
- Los proyectos nuevos generados a partir de las plantillas incluidas dejarán de marcar los roles **UX** y **Design** como participantes de estimación por defecto.
- Se mantiene al menos un rol computable para garantizar la funcionalidad de estimaciones.

## Verificación
- Validación sintáctica del fixture mediante `python -m json.tool taiga/projects/fixtures/initial_project_templates.json`.
 
## Pasos posteriores
- Tras modificar el fixture, ejecutar desde el backend (virtualenv activo) el comando:

	```bash
	python manage.py loaddata taiga/projects/fixtures/initial_project_templates.json
	```

- En producción, aplicar el mismo `loaddata` tras desplegar el cambio (por ejemplo integrándolo en el playbook de despliegue o ejecutándolo manualmente en el servidor). Como alternativa, incluir la actualización en una migración de datos específica para que se ejecute automáticamente durante el despliegue.

## Archivos modificados
- `taiga/projects/fixtures/initial_project_templates.json`
