CALL () {
  // 1. Find Reporter-Assignee loops on Jira Issues (Weight: 2)
  MATCH (reporter:Person)-[:REPORTED_BY]-(work:Issue)-[:ASSIGNED_TO]-(assignee:Person)
  WHERE $include_reporter_assignee
    AND elementId(reporter) <> elementId(assignee)
    AND work.created_at >= datetime() - duration({days: $lookback_days})
  WITH 
    CASE WHEN elementId(reporter) < elementId(assignee) THEN reporter ELSE assignee END AS p1,
    CASE WHEN elementId(reporter) < elementId(assignee) THEN assignee ELSE reporter END AS p2,
    work
  RETURN p1, p2, count(work) * $weight_reporter_assignee AS sub_score
  
  UNION ALL
  
  // 2. Find GitHub PR Reviews (Weight: 3)
  MATCH (reviewer:Person)<-[:REVIEWED_BY|REQUESTED_REVIEWER]-(pr:PullRequest)-[:CREATED_BY]->(author:Person)
  WHERE $include_pr_reviews
    AND elementId(reviewer) <> elementId(author)
    AND pr.created_at >= datetime() - duration({days: $lookback_days})
  WITH 
    CASE WHEN elementId(reviewer) < elementId(author) THEN reviewer ELSE author END AS p1,
    CASE WHEN elementId(reviewer) < elementId(author) THEN author ELSE reviewer END AS p2,
    pr
  RETURN p1, p2, count(pr) * $weight_pr_reviews AS sub_score

  UNION ALL
  
  // 3. Find Shared Commits on same File (Weight: 5)
  MATCH (dev1:Person)<-[:AUTHORED_BY]-(c1:Commit)-[:MODIFIES]->(f:File)<-[:MODIFIES]-(c2:Commit)-[:AUTHORED_BY]->(dev2:Person)
  WHERE $include_shared_file_commits
    AND elementId(dev1) <> elementId(dev2)
    AND c1.created_at >= datetime() - duration({days: $lookback_days})
    AND c2.created_at >= datetime() - duration({days: $lookback_days})
    AND NOT any(suffix IN $excluded_file_suffixes WHERE f.name ENDS WITH suffix)
  WITH CASE WHEN elementId(dev1) < elementId(dev2) THEN dev1 ELSE dev2 END AS p1,
       CASE WHEN elementId(dev1) < elementId(dev2) THEN dev2 ELSE dev1 END AS p2, f
  RETURN p1, p2, count(DISTINCT f) * $weight_shared_file_commits AS sub_score

  UNION ALL

  // 4. Find Sprint Co-workers (Weight: 2)
  // Captures pairs assigned to different issues within the exact same Sprint
  MATCH (dev1:Person)-[:ASSIGNED_TO]-(i1:Issue)-[:IN_SPRINT]->(s:Sprint)<-[:IN_SPRINT]-(i2:Issue)-[:ASSIGNED_TO]-(dev2:Person)
  WHERE $include_sprint_coworkers
    AND elementId(dev1) < elementId(dev2)
    AND i1.created_at >= datetime() - duration({days: $lookback_days})
    AND i2.created_at >= datetime() - duration({days: $lookback_days})
  WITH dev1 AS p1, dev2 AS p2, s
  RETURN p1, p2, count(DISTINCT s) * $weight_sprint_coworkers AS sub_score

  UNION ALL

  // 5. Find Explicit Review Requests (Bonus Weight: 2)
  // Gives extra points on top of general PR interactions when a review is actively requested
  MATCH (reviewer:Person)<-[:REQUESTED_REVIEWER]-(pr:PullRequest)-[:CREATED_BY]->(author:Person)
  WHERE $include_explicit_review_requests
    AND elementId(reviewer) <> elementId(author)
    AND pr.created_at >= datetime() - duration({days: $lookback_days})
  WITH CASE WHEN elementId(reviewer) < elementId(author) THEN reviewer ELSE author END AS p1,
       CASE WHEN elementId(reviewer) < elementId(author) THEN author ELSE reviewer END AS p2, pr
  RETURN p1, p2, count(pr) * $weight_explicit_review_requests AS sub_score

  UNION ALL

  // 6. Find Epic Overlap (Weight: 1)
  // Weak but aggregate signal for people working under the same large initiative
  MATCH (dev1:Person)-[:ASSIGNED_TO]-(i1:Issue)-[:PART_OF]-(e:Epic)-[:PART_OF]-(i2:Issue)-[:ASSIGNED_TO]-(dev2:Person)
  WHERE $include_epic_overlap
    AND elementId(dev1) < elementId(dev2)
    AND i1.created_at >= datetime() - duration({days: $lookback_days})
    AND i2.created_at >= datetime() - duration({days: $lookback_days})
  WITH dev1 AS p1, dev2 AS p2, e
  RETURN p1, p2, count(DISTINCT e) * $weight_epic_overlap AS sub_score
}
// Sum the scores from all independent systems
WITH p1, p2, sum(sub_score) AS total_collaboration_score
WHERE total_collaboration_score >= $min_pair_score
  AND (
    NOT $exclude_bots
    OR (
      NOT p1.name ENDS WITH '[bot]'
      AND NOT p2.name ENDS WITH '[bot]'
    )
  )
RETURN p1.name AS person1, p2.name AS person2, total_collaboration_score
ORDER BY total_collaboration_score DESC