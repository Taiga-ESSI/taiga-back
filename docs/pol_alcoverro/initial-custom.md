# Informe de cambios — rama `feat/1/initial-custom`

## Resumen ejecutivo
- Se enriquecen las plantillas iniciales con nuevos campos personalizados y se ajustan los roles UX/Design para que no computen en estimaciones por defecto.
- Se crea y aplica la migración `0068_add_priority_custom_attribute` para sincronizar los nuevos campos en plantillas existentes y se corrige el manejo del atributo `extra` al exportar/importar plantillas.

## Detalle de modificaciones

### Plantillas iniciales de proyectos

#### Roles y módulos activos
- Se fijan los roles `ux` y `design` con `"computable": false` en ambos templates (`scrum`, `kanban`) para desactivar el toggle `help_role_enabled` por defecto y evitar que participen en la estimación.
- Se mantiene activado el módulo de épicas en Scrum y se desactiva la wiki en las plantillas donde aplica para simplificar el onboarding según las necesidades del TFG.

#### Nuevos custom fields
- **Fixture:** `taiga/projects/fixtures/initial_project_templates.json` añade cuatro atributos predeterminados:
  - User Story → **Priority** (`dropdown` con opciones `Low`, `Medium`, `High`).
  - User Story → **Acceptance Criteria** (`richtext`).
  - Task → **Estimated Effort** (`number`).
  - Task → **Actual Effort** (`number`).
- **Migración:** `taiga/projects/migrations/0068_add_priority_custom_attribute.py` inserta estos campos en plantillas existentes respetando el orden previo y evitando duplicidades. El script recalcula el `order` en función de los atributos ya almacenados y ofrece reversión limpia en `reverse_code`.

#### Preservar metadatos `extra`
- **Archivo:** `taiga/projects/models.py`.
- **Cambio clave:** Al exportar (`load_data_from_project`) y aplicar (`apply_to_project`) plantillas se incluye el campo `extra` para todos los tipos de custom attributes (epic, US, task e issue), evitando perder opciones como los valores del dropdown de prioridad.

## Verificación realizada
- Reaplicación dirigida de la migración para validar los datos insertados:

    ```bash
    python manage.py migrate projects 0067
    python manage.py migrate projects 0068
    ```

- Creación de proyectos piloto a partir de los templates `scrum` y `kanban` comprobando en *Admin → Custom fields* la presencia de los cuatro atributos y que el campo **Priority** despliega las opciones configuradas.

## Archivos tocados
- `taiga/projects/fixtures/initial_project_templates.json`
- `taiga/projects/migrations/0068_add_priority_custom_attribute.py`
- `taiga/projects/models.py`
