## Branch
- Around 10-30% of branches have empty or null attributes, because they are not default branch. We keep track of them to complete the relation of a PR. Its generally the src branch of the PR where we are not collecting all attributes. Its not needed under the current requirements.

## Commit
- All attributes are populated. 

## Epic
- due_date is empty for some Epics. Acceptable.

## File
- All attributes are populated.

## IdentityMapping
- email may be absent. Acceptable.

## Initiative
- due_date, labels and components may be absent. Acceptable.

## Issue
- Some of the issues are stub issues as they were discovered as a linked issue and did not match the scan conditions. Eg: Scan condition=last-30-days. An issue within last 30 days was linked to an issue which was created prior to last 30 days.
Around 10% such issues are acceptable.

## Person
- title, role, senriority, hire_date are not implemented yet.
- email is sometimes absent too for a small (<10%) of users -- typically bots and automation users or partially deleted users.

## Project
-  All attributes are populated.

## Pull Request
- labels, merged_at and closed_at can be empty for some PRs.

## Repository
-  All attributes are populated.

## Sprint
- start_date and end_date can be empty for some (10% missing acceptable)
- goal may be missing for any number of sprints. 

## Team 
-  All attributes are populated.

## COLLABORATOR
- role may be empty. It is set when for users in github in relation to repo, as of now.

## MODIFIED_BY
-  All attributes are populated.

## MODIFIES
-  All attributes are populated.

## REVIEWED
-  All attributes are populated.

## REVIEWED_BY
-  All attributes are populated.

