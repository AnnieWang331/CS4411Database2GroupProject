-- The same demo room as scripts/seed.py, then the board as the app would load it.
-- Run after schema.sql and queries.sql (psql, since it uses \gset to keep the ids).

SET search_path = brainstorm;

SELECT room_id, code
  FROM create_room('prof-demo', 'How should we index a classroom brainstorm board?') \gset

SELECT join_room(:'room_id', 'stu-annie', 'Annie'),
       join_room(:'room_id', 'stu-roah', 'Roah'),
       join_room(:'room_id', 'stu-sachin', 'Sachin'),
       join_room(:'room_id', 'stu-haadi', 'Haadi') \g /dev/null

SELECT idea_id AS idea1 FROM post_idea(:'room_id', 'stu-annie',
    'Keep every room in one partition so one Query loads the board') \gset
SELECT idea_id AS idea2 FROM post_idea(:'room_id', 'stu-roah',
    'Store vote counts on the idea with an atomic counter') \gset
SELECT idea_id AS idea3 FROM post_idea(:'room_id', 'stu-sachin',
    'Use TTL so rooms clean themselves up after class') \gset
SELECT idea_id AS idea4 FROM post_idea(:'room_id', 'stu-haadi',
    'Push new ideas to clients with DynamoDB Streams') \gset

SELECT vote(:'room_id', 'stu-roah', :'idea1'),
       vote(:'room_id', 'stu-sachin', :'idea1'),
       vote(:'room_id', 'stu-haadi', :'idea1'),
       vote(:'room_id', 'stu-annie', :'idea2'),
       vote(:'room_id', 'stu-haadi', :'idea2'),
       vote(:'room_id', 'stu-annie', :'idea3') \g /dev/null

SELECT add_comment(:'room_id', 'stu-sachin', :'idea1', 'And it avoids joins entirely'),
       add_comment(:'room_id', 'stu-annie', :'idea4', 'Streams plus a WebSocket API Gateway')
       \g /dev/null

\echo
\echo Room :room_id  code :code
\echo

-- Pattern 10: the board, top-voted first, with each idea's comments.
SELECT t.vote_count AS votes, t.author_name AS author, t.body AS idea,
       coalesce(string_agg(c.author_name || ': ' || c.body, E'\n' ORDER BY c.created_at), '')
           AS comments
  FROM top_ideas(:'room_id') t
  LEFT JOIN room_comments(:'room_id') c USING (idea_id)
 GROUP BY t.idea_id, t.vote_count, t.author_name, t.body, t.created_at
 ORDER BY t.vote_count DESC, t.created_at;
