# Executive Dashboard Design System

This document describes the centralized design system for the AI Tech Lead application's frontend. All design tokens, components, and styling patterns are defined in `app/dash_app/styles.py` and `app/dash_app/assets/executive-dashboard.css`.

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Color Palette](#color-palette)
3. [Typography](#typography)
4. [Spacing System](#spacing-system)
5. [Components](#components)
6. [CSS Variables](#css-variables)
7. [Usage Examples](#usage-examples)

---

## Design Philosophy

The Executive Dashboard aesthetic prioritizes:

- **Clarity**: Clean layouts with ample whitespace
- **Professionalism**: Refined typography using Cormorant Garamond (serif) and Inter (sans-serif)
- **Consistency**: Centralized design tokens prevent style drift
- **Accessibility**: Sufficient color contrast and readable font sizes
- **Restraint**: Navy accent color (#2c5282) used sparingly for emphasis

---

## Color Palette

### Primary Colors

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR_NAVY` | `#2c5282` | Primary accent (buttons, active states, headings) |
| `COLOR_NAVY_DARK` | `#1e3a5f` | Hover states for navy elements |
| `COLOR_NAVY_HOVER` | `#234164` | Alternative hover state |

### Text Colors

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR_CHARCOAL` | `#1a202c` | Darkest text (headings) |
| `COLOR_CHARCOAL_MEDIUM` | `#2d3748` | Primary body text |
| `COLOR_GRAY_DARK` | `#4a5568` | Secondary text |
| `COLOR_GRAY_MEDIUM` | `#718096` | Tertiary text, labels |
| `COLOR_GRAY_LIGHT` | `#a0aec0` | Muted text, placeholders |
| `COLOR_GRAY_LIGHTER` | `#cbd5e0` | Borders, dividers, icons |

### Background Colors

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR_BACKGROUND_WHITE` | `#ffffff` | Main backgrounds, cards |
| `COLOR_BACKGROUND_LIGHT` | `#f7fafc` | Alternate backgrounds, input fields |
| `COLOR_SURFACE_ACTIVE` | `#edf2f7` | Active navigation items |

### Border Colors

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR_BORDER` | `#e2e8f0` | Standard borders |
| `COLOR_BORDER_LIGHT` | `#e2e8f0` | Light borders (same as standard) |

### Utility Colors

| Token | Value | Usage |
|-------|-------|-------|
| `COLOR_SUCCESS` | `#48bb78` | Success messages, positive indicators |
| `COLOR_WARNING` | `#ed8936` | Warning messages, caution indicators |
| `COLOR_ERROR` | `#f56565` | Error messages, critical alerts |
| `COLOR_INFO` | `#4299e1` | Informational messages |

---

## Typography

### Font Families

| Token | Value | Usage |
|-------|-------|-------|
| `FONT_SERIF` | `'Cormorant Garamond', serif` | Decorative elements (diamond icons, accents) |
| `FONT_SANS` | `'Inter', sans-serif` | All body text, UI elements |

**Google Fonts Import** (included in layout.py):
```
https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;600;700&family=Inter:wght@300;400;500;600&display=swap
```

### Font Sizes

| Token | Value | Usage |
|-------|-------|-------|
| `FONT_SIZE_XLARGE` | `42px` | Large decorative text |
| `FONT_SIZE_LARGE` | `15px` | Section headings |
| `FONT_SIZE_MEDIUM` | `14px` | Body text |
| `FONT_SIZE_SMALL` | `13px` | Small text, labels |
| `FONT_SIZE_XSMALL` | `12px` | Tiny text, captions |
| Not defined (use `11px`) | `11px` | Helper text, footnotes |

### Font Weights

| Token | Value | Usage |
|-------|-------|-------|
| `FONT_WEIGHT_NORMAL` | `400` | Body text |
| `FONT_WEIGHT_MEDIUM` | `500` | Emphasized text |
| `FONT_WEIGHT_SEMIBOLD` | `600` | Headings, active states |
| `FONT_WEIGHT_BOLD` | `700` | Strong emphasis |

---

## Spacing System

Follows a consistent 4px/8px grid system:

| Token | Value | Usage |
|-------|-------|-------|
| `SPACING_XXXSMALL` | `4px` | Tight spacing |
| `SPACING_XXSMALL` | `8px` | Minimal spacing |
| `SPACING_XSMALL` | `12px` | Small spacing, margins |
| `SPACING_SMALL` | `16px` | Standard padding |
| `SPACING_MEDIUM` | `24px` | Section spacing |
| `SPACING_LARGE` | `32px` | Large gaps |
| `SPACING_XLARGE` | `40px` | Extra large gaps |
| `SPACING_XXLARGE` | `48px` | Maximum spacing |

**Design Rule**: Always use spacing tokens instead of hardcoded pixel values.

---

## Components

### Page Headers

**Style Token**: `PAGE_HEADER_STYLE`

```python
from app.dash_app.components.common import create_page_header

# Usage
header = create_page_header("My Page Title")
```

**Visual**: Uppercase text with 1.5px letter spacing, gray color, bottom border

---

### Feature Cards

**Style Tokens**: `FEATURE_CARD_STYLE`, `FEATURE_CARD_TITLE_STYLE`, `FEATURE_CARD_DESCRIPTION_STYLE`

```python
from app.dash_app.components.common import create_feature_card

# Usage
card = create_feature_card(
    title="Feature Name",
    description="Description of the feature",
    icon="fas fa-chart-line"
)
```

**Visual**: Light gray background with navy left border accent

---

### Chat Messages

**Style Tokens**: `CHAT_MESSAGE_USER_STYLE`, `CHAT_MESSAGE_AI_STYLE`, `CHAT_MESSAGE_TIMESTAMP_STYLE`, etc.

```python
from app.dash_app.components.common import create_user_message, create_ai_message

# Usage
user_msg = create_user_message(text="Hello", timestamp="10:30 AM")
ai_msg = create_ai_message(text="Hi there!", timestamp="10:30 AM")
```

**Visual**: 
- User messages: Navy background with white text, right-aligned
- AI messages: Light gray background with charcoal text, left-aligned

---

### Placeholder Sections

**Style Tokens**: `PLACEHOLDER_ICON_STYLE`, `PLACEHOLDER_MESSAGE_STYLE`

```python
from app.dash_app.components.common import create_placeholder_section

# Usage
placeholder = create_placeholder_section(
    icon="fas fa-inbox",
    message="No data available"
)
```

**Visual**: Centered gray icon with italic message text

---

### Navigation

**Style Tokens**: `SIDEBAR_STYLE`, `NAVBAR_BRAND_STYLE`, `TOPBAR_STYLE`, etc.

**CSS Classes**: `.executive-sidebar`, `.executive-nav-link`, `.executive-topbar`

**Visual**:
- Sidebar: White background, vertical nav links
- Nav links: Gray text, navy left border when active
- Topbar: White background with bottom border

---

### Graph Components

**Style Tokens**: `GRAPH_SECTION_CONTAINER_STYLE`, `GRAPH_QUERY_TEXTAREA_STYLE`, `GRAPH_EXECUTE_BUTTON_STYLE`, etc.

**Visual**:
- Query console: Light gray background container
- Execute button: Navy button matching primary color
- Graph: White background with light gray border

---

## CSS Variables

All CSS variables are defined in `app/dash_app/assets/executive-dashboard.css`:

```css
:root {
    /* Colors */
    --color-navy: #2c5282;
    --color-charcoal-medium: #2d3748;
    --color-background-light: #f7fafc;
    
    /* Typography */
    --font-sans: 'Inter', sans-serif;
    --font-size-small: 13px;
    
    /* Spacing */
    --spacing-small: 16px;
    
    /* Transitions */
    --transition-base: 0.2s ease;
}
```

**Usage in custom CSS**:

```css
.my-custom-class {
    color: var(--color-navy);
    font-family: var(--font-sans);
    padding: var(--spacing-small);
}
```

---

## Usage Examples

### Creating a New Page

```python
from dash import html
import dash_bootstrap_components as dbc
from app.dash_app.components.common import create_page_header, create_feature_card
from app.dash_app.styles import CARD_CONTAINER_STYLE

def get_layout():
    return html.Div([
        # Page header
        create_page_header("My New Page"),
        
        # Card container
        html.Div([
            create_feature_card(
                title="Feature 1",
                description="Description here",
                icon="fas fa-rocket"
            ),
            create_feature_card(
                title="Feature 2",
                description="Another description",
                icon="fas fa-chart-bar"
            )
        ], style=CARD_CONTAINER_STYLE)
    ])
```

---

### Using Design Tokens Directly

```python
from dash import html
from app.dash_app.styles import (
    COLOR_NAVY,
    FONT_SANS,
    SPACING_MEDIUM,
    SPACING_SMALL
)

custom_div = html.Div(
    "Custom Content",
    style={
        "color": COLOR_NAVY,
        "fontFamily": FONT_SANS,
        "padding": f"{SPACING_SMALL} {SPACING_MEDIUM}",
        "borderRadius": "2px"
    }
)
```

---

### Merging Styles

```python
from app.dash_app.styles import FEATURE_CARD_STYLE, merge_styles

custom_card_style = merge_styles(
    FEATURE_CARD_STYLE,
    {"boxShadow": "0 4px 6px rgba(0,0,0,0.1)"}
)

card = html.Div("Content", style=custom_card_style)
```

---

### Custom CSS with Variables

```css
/* In executive-dashboard.css or custom stylesheet */

.my-page-specific-class {
    background-color: var(--color-background-light);
    border: 1px solid var(--color-border);
    padding: var(--spacing-medium);
    font-family: var(--font-sans);
    font-size: var(--font-size-small);
    color: var(--color-charcoal-medium);
    transition: all var(--transition-base);
}

.my-page-specific-class:hover {
    background-color: var(--color-surface-active);
    border-color: var(--color-navy);
}
```

---

## Best Practices

1. **Always use design tokens**: Never hardcode colors, fonts, or spacing values
2. **Use helper components**: Prefer `create_page_header()` over custom implementations
3. **Keep CSS minimal**: Use Python style dictionaries for most styling
4. **Use CSS for interactions**: Hover states, animations, and transitions belong in CSS
5. **Maintain consistency**: If a pattern exists, reuse it instead of creating variations
6. **Test visual regression**: Verify no visual changes when refactoring styles

---

## Maintenance

### Adding New Colors

1. Add constant to `app/dash_app/styles.py`:
   ```python
   COLOR_NEW = "#hexcode"
   ```

2. Add CSS variable to `app/dash_app/assets/executive-dashboard.css`:
   ```css
   :root {
       --color-new: #hexcode;
   }
   ```

### Adding New Components

1. Add component function to `app/dash_app/components/common.py`
2. Add style constants to `app/dash_app/styles.py`
3. Document in this file under "Components" section
4. Add usage example

### Updating Existing Styles

1. Change the constant value in `styles.py`
2. Update corresponding CSS variable if applicable
3. Verify all pages still look correct
4. Run linting to ensure no errors

---

## File Structure

```
app/dash_app/
├── styles.py                     # Python design tokens (single source of truth)
├── components/
│   └── common.py                 # Reusable UI components
├── assets/
│   └── executive-dashboard.css   # CSS animations, interactions, variables
└── pages/
    ├── chat.py                   # Chat page
    ├── people.py                 # People page
    ├── progress.py               # Progress page
    ├── settings.py               # Settings page
    └── graph/
        └── layout.py             # Graph visualization page
```

---

## Version History

- **v1.0** (Current): Initial design system implementation
  - Centralized all design tokens in `styles.py`
  - Created reusable components in `common.py`
  - Converted CSS to use variables
  - Refactored all pages to use design system
