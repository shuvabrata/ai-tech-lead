# Jira Integration TODO

## Sprint Field Custom ID Issue

**Priority:** Medium  
**Status:** Not Started

### Problem

The sprint field ID is hardcoded as `customfield_10020` in two locations:
- [`main.py`](main.py) line 217 in `extract_sprint_ids_from_issues()`
- [`new_issue_handler.py`](new_issue_handler.py) line 139 in `new_issue_handler()`

This field ID varies across different Jira instances. Common variations include:
- `customfield_10020` (current default)
- `customfield_10001`
- `customfield_10016`
- `customfield_10026`
- Or any other custom field ID depending on instance configuration

### Impact

If the Jira instance uses a different custom field ID for sprints:
- Sprint extraction will fail silently
- No sprint IDs will be found in issues
- Sprint nodes won't be created
- Issue-Sprint relationships won't be established

### Proposed Solutions

**Option 1: Environment Variable (Quick Fix)**
```python
SPRINT_FIELD_ID = os.getenv('JIRA_SPRINT_FIELD_ID', 'customfield_10020')
sprint_field = fields.get('sprint') or fields.get(SPRINT_FIELD_ID, [])
```

**Option 2: Config File (Better)**
Add to `.config.json`:
```json
{
  "custom_fields": {
    "sprint": "customfield_10020",
    "story_points": "customfield_10016",
    "epic_link": "customfield_10014"
  }
}
```

**Option 3: Auto-Detection (Best)**
- Try multiple common field IDs
- Detect which one contains sprint data
- Cache the detected field ID
- Log a warning if using fallback detection

**Option 4: Field Discovery Tool**
Create a utility script to:
- Fetch a sample issue
- List all custom fields and their values
- Identify which field contains sprint information
- Output the correct field ID for configuration

### Files to Update

1. `main.py` - `extract_sprint_ids_from_issues()` function
2. `new_issue_handler.py` - Sprint field extraction logic
3. Potentially add similar configurability for:
   - Story points field (`customfield_10016` or `customfield_10026`)
   - Epic link field (`customfield_10014`)

### Related Issues

- Same pattern exists for story points extraction (also hardcoded)
- Epic link field may also need similar treatment

### Acceptance Criteria

- [ ] Sprint field ID is configurable
- [ ] Default value still works for common configurations
- [ ] Clear documentation on how to find the correct field ID
- [ ] Logging indicates which field ID is being used
- [ ] Works across different Jira instances without code changes

---

## Future Enhancements

### Custom Issue Types Support
- Currently hardcoded: Story, Bug, Task
- Should be configurable via environment or config file
- Reference: Asked about in initial requirements but deferred

### Additional Sprint Field Variations
- Some instances use `sprint` as standard field name
- Some use custom field arrays vs single objects
- Current code handles both, but could be more robust
