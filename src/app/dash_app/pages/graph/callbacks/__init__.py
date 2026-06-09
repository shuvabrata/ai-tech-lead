"""Callbacks Package

Imports all graph page callbacks to register them with Dash.
"""

# Import all callbacks to register them
from .query import validate_query, execute_query, toggle_query_collapse
from .catalog import (
    load_query_catalog,
    populate_namespace_filter,
    sync_selected_catalog_query,
    render_catalog_query_list,
    render_catalog_query_detail,
    sync_catalog_parameter_values,
    load_catalog_query_into_console,
)
from .display import display_properties, update_layout
from .expansion import (
    execute_doubleclick_expansion,
    open_expansion_modal,
    close_expansion_modal,
    execute_node_expansion
)
from .context_menu import (
    show_context_menu,
    context_menu_expand_modal,
    context_menu_quick_expand,
    hide_menu_after_copy,
    context_menu_remove_node,
    context_menu_keep_neighbours,
)
from .navigation import handle_keyboard_shortcuts
from .filtering import (
    toggle_filter_panel,
    update_relationship_type_filter,
    update_filter_panel_feedback,
    update_weight_threshold_label,
    clear_all_filters,
    apply_relationship_filters
)
from .analytics_mode import toggle_query_panel_for_analytics_mode
from .spotlight import update_spotlight

__all__ = [
    # Query callbacks
    'validate_query',
    'execute_query',
    'toggle_query_collapse',
    'load_query_catalog',
    'populate_namespace_filter',
    'sync_selected_catalog_query',
    'render_catalog_query_list',
    'render_catalog_query_detail',
    'sync_catalog_parameter_values',
    'load_catalog_query_into_console',
    # Display callbacks
    'display_properties',
    'update_layout',
    # Expansion callbacks
    'execute_doubleclick_expansion',
    'open_expansion_modal',
    'close_expansion_modal',
    'execute_node_expansion',
    # Context menu callbacks
    'show_context_menu',
    'context_menu_expand_modal',
    'context_menu_quick_expand',
    'hide_menu_after_copy',
    'context_menu_remove_node',
    'context_menu_keep_neighbours',
    # Navigation callbacks
    'handle_keyboard_shortcuts',
    # Filtering callbacks (Phase 1.2.4)
    'toggle_filter_panel',
    'update_relationship_type_filter',
    'update_filter_panel_feedback',
    'update_weight_threshold_label',
    'clear_all_filters',
    'apply_relationship_filters',
    'toggle_query_panel_for_analytics_mode',
]
