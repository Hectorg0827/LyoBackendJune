-- Seed Study Groups
INSERT INTO study_groups (name, description, creator_id, status, privacy, requires_approval, created_at, updated_at) VALUES 
('SwiftUI Masterminds', 'Deep dive into advanced SwiftUI animations and state management.', 1, 'active', 'public', 0, datetime('now'), datetime('now')),
('Python for Data Science', 'Weekly sessions covering Pandas, NumPy, and Scikit-Learn.', 2, 'active', 'public', 0, datetime('now'), datetime('now')),
('AI Engineering', 'Building and deploying LLM-based applications.', 3, 'active', 'public', 0, datetime('now'), datetime('now'));

-- Seed Community Events
INSERT INTO community_events (title, description, event_type, status, location, room_id, latitude, longitude, is_online, timezone, start_time, end_time, organizer_id, created_at, updated_at) VALUES 
('SwiftUI Animations Deep Dive', 'Detailed session about advanced SwiftUI animations.', 'workshop', 'scheduled', 'Innovation Lab Room 1', 'room-1', 37.775, -122.419, 0, 'UTC', datetime('now', '+2 days'), datetime('now', '+2 days', '+2 hours'), 1, datetime('now'), datetime('now')),
('Career Advice Office Hours', 'Drop in for career guidance and resume reviews.', 'office_hours', 'scheduled', 'Career Center', 'room-2', 37.776, -122.420, 0, 'UTC', datetime('now', '+1 days'), datetime('now', '+1 days', '+1 hours'), 2, datetime('now'), datetime('now')),
('Networking Mixer', 'Connect with other students and industry professionals.', 'networking', 'scheduled', 'Campus Plaza', 'plaza-1', 37.774, -122.418, 0, 'UTC', datetime('now', '+3 days'), datetime('now', '+3 days', '+3 hours'), 3, datetime('now'), datetime('now'));

-- Seed Marketplace Items
INSERT INTO marketplace_items (title, description, price, currency, latitude, longitude, location_name, image_urls, seller_id, is_active, is_sold, created_at, updated_at) VALUES 
('Cracking the Coding Interview', 'Used book, great condition.', 25.0, 'USD', 37.775, -122.419, 'Campus Bookstore', '["https://picsum.photos/200/300"]', 1, 1, 0, datetime('now'), datetime('now')),
('MacBook Pro Stand', 'Ergonomic aluminum stand.', 15.0, 'USD', 37.776, -122.420, 'Library', '["https://picsum.photos/200/301"]', 2, 1, 0, datetime('now'), datetime('now')),
('Calculus 101 Textbook', 'Required for CS freshmen.', 30.0, 'USD', 37.774, -122.418, 'Student Union', '["https://picsum.photos/200/302"]', 3, 1, 0, datetime('now'), datetime('now'));
