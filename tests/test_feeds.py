"""
Test cases for feeds endpoints.
Tests post creation, comments, reactions, and social features.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AsyncTestCase, assert_successful_response, assert_error_response, assert_pagination_response


class TestPostManagement(AsyncTestCase):
    """Test post creation and management."""

    async def test_create_text_post(self, async_test_client: AsyncClient):
        """Test creating a text post."""
        # Create user
        user_data = {
            "email": "postuser@example.com",
            "username": "postuser",
            "password": "password123",
            "full_name": "Post User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create post
        post_data = {
            "content": "This is my first post! #hello #world",
            "tags": ["hello", "world"],
            "is_public": True
        }

        response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["content"] == post_data["content"]
        assert data["tags"] == post_data["tags"]
        assert data["is_public"] == post_data["is_public"]
        assert "author" in data
        assert data["author"]["username"] == user_data["username"]
        assert data["likes"] == 0
        assert data["comments"] == 0

    async def test_create_post_with_images(self, async_test_client: AsyncClient):
        """Test creating a post with images."""
        # Create user
        user_data = {
            "email": "imageuser@example.com",
            "username": "imageuser",
            "password": "password123",
            "full_name": "Image User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create post with images
        post_data = {
            "content": "Check out these amazing photos!",
            "image_urls": [
                "https://example.com/image1.jpg",
                "https://example.com/image2.jpg",
                "https://example.com/image3.jpg"
            ],
            "tags": ["photos", "amazing"],
            "is_public": True
        }

        response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["content"] == post_data["content"]
        assert data["image_urls"] == post_data["image_urls"]
        assert len(data["image_urls"]) == 3

    async def test_create_post_with_video(self, async_test_client: AsyncClient):
        """Test creating a post with video."""
        # Create user
        user_data = {
            "email": "videouser@example.com",
            "username": "videouser",
            "password": "password123",
            "full_name": "Video User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create post with video
        post_data = {
            "content": "Watch this awesome video!",
            "video_url": "https://example.com/video.mp4",
            "tags": ["video", "awesome"],
            "is_public": True
        }

        response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["content"] == post_data["content"]
        assert data["video_url"] == post_data["video_url"]

    async def test_get_feed_posts(self, async_test_client: AsyncClient):
        """Test getting feed posts."""
        response = await async_test_client.get("/api/v1/feeds/posts")

        assert_successful_response(response, 200)
        data = response.json()

        assert_pagination_response(response)

    async def test_get_user_posts(self, async_test_client: AsyncClient):
        """Test getting posts by specific user."""
        # Create user and posts
        user_data = {
            "email": "userposts@example.com",
            "username": "userposts",
            "password": "password123",
            "full_name": "User Posts"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create multiple posts
        for i in range(3):
            post_data = {
                "content": f"This is post number {i+1}",
                "tags": [f"post{i+1}"],
                "is_public": True
            }
            await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)

        # Get user's posts
        response = await async_test_client.get(f"/api/v1/feeds/users/{user_data['username']}/posts")

        assert_successful_response(response, 200)
        data = response.json()

        assert len(data["items"]) == 3
        assert_pagination_response(response, 3)

    async def test_update_post(self, async_test_client: AsyncClient):
        """Test updating a post."""
        # Create user and post
        user_data = {
            "email": "updatepost@example.com",
            "username": "updatepost",
            "password": "password123",
            "full_name": "Update Post User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create post
        post_data = {
            "content": "Original post content",
            "tags": ["original"],
            "is_public": True
        }

        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)
        post_id = create_response.json()["id"]

        # Update post
        update_data = {
            "content": "Updated post content",
            "tags": ["updated"],
            "is_public": False
        }

        response = await async_test_client.put(f"/api/v1/feeds/posts/{post_id}", json=update_data, headers=headers)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["content"] == update_data["content"]
        assert data["tags"] == update_data["tags"]
        assert data["is_public"] == update_data["is_public"]

    async def test_delete_post(self, async_test_client: AsyncClient):
        """Test deleting a post."""
        # Create user and post
        user_data = {
            "email": "deletepost@example.com",
            "username": "deletepost",
            "password": "password123",
            "full_name": "Delete Post User"
        }

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create post
        post_data = {
            "content": "Post to be deleted",
            "is_public": True
        }

        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)
        post_id = create_response.json()["id"]

        # Delete post
        response = await async_test_client.delete(f"/api/v1/feeds/posts/{post_id}", headers=headers)

        assert_successful_response(response, 204)

        # Verify post is deleted
        get_response = await async_test_client.get(f"/api/v1/feeds/posts/{post_id}")
        assert_error_response(get_response, 404, "POST_NOT_FOUND")

    async def test_delete_other_user_post_fails(self, async_test_client: AsyncClient):
        """Test that users cannot delete other users' posts."""
        # Create two users
        user1_data = {
            "email": "user1@example.com",
            "username": "user1",
            "password": "password123",
            "full_name": "User One"
        }

        user2_data = {
            "email": "user2@example.com",
            "username": "user2",
            "password": "password123",
            "full_name": "User Two"
        }

        await async_test_client.post("/api/v1/auth/register", json=user1_data)
        await async_test_client.post("/api/v1/auth/register", json=user2_data)

        # User 1 creates a post
        login1_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user1_data["email"],
            "password": user1_data["password"]
        })

        token1 = login1_response.json()["access_token"]
        headers1 = {"Authorization": f"Bearer {token1}"}

        post_data = {"content": "User 1's post", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers1)
        post_id = create_response.json()["id"]

        # User 2 tries to delete User 1's post
        login2_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user2_data["email"],
            "password": user2_data["password"]
        })

        token2 = login2_response.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        response = await async_test_client.delete(f"/api/v1/feeds/posts/{post_id}", headers=headers2)

        assert_error_response(response, 403, "INSUFFICIENT_PERMISSIONS")


class TestPostInteractions(AsyncTestCase):
    """Test post interactions like likes, comments, and shares."""

    async def test_like_post(self, async_test_client: AsyncClient):
        """Test liking a post."""
        # Create two users
        author_data = {
            "email": "author@example.com",
            "username": "author",
            "password": "password123",
            "full_name": "Post Author"
        }

        liker_data = {
            "email": "liker@example.com",
            "username": "liker",
            "password": "password123",
            "full_name": "Post Liker"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=liker_data)

        # Author creates post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post to be liked", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Liker likes the post
        login_liker = await async_test_client.post("/api/v1/auth/login", json={
            "email": liker_data["email"],
            "password": liker_data["password"]
        })

        token_liker = login_liker.json()["access_token"]
        headers_liker = {"Authorization": f"Bearer {token_liker}"}

        response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/like", headers=headers_liker)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["liked"] == True

        # Check if like count increased
        get_response = await async_test_client.get(f"/api/v1/feeds/posts/{post_id}")
        post_data = get_response.json()
        assert post_data["likes"] == 1

    async def test_unlike_post(self, async_test_client: AsyncClient):
        """Test unliking a post."""
        # Create users and post, then like it
        author_data = {
            "email": "unlike_author@example.com",
            "username": "unlike_author",
            "password": "password123",
            "full_name": "Unlike Author"
        }

        liker_data = {
            "email": "unlike_liker@example.com",
            "username": "unlike_liker",
            "password": "password123",
            "full_name": "Unlike Liker"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=liker_data)

        # Create post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post to be unliked", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Like the post
        login_liker = await async_test_client.post("/api/v1/auth/login", json={
            "email": liker_data["email"],
            "password": liker_data["password"]
        })

        token_liker = login_liker.json()["access_token"]
        headers_liker = {"Authorization": f"Bearer {token_liker}"}

        await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/like", headers=headers_liker)

        # Unlike the post
        response = await async_test_client.delete(f"/api/v1/feeds/posts/{post_id}/like", headers=headers_liker)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["liked"] == False

        # Check if like count decreased
        get_response = await async_test_client.get(f"/api/v1/feeds/posts/{post_id}")
        post_data = get_response.json()
        assert post_data["likes"] == 0

    async def test_duplicate_like_fails(self, async_test_client: AsyncClient):
        """Test that liking a post twice fails."""
        # Create users and post
        author_data = {
            "email": "dup_author@example.com",
            "username": "dup_author",
            "password": "password123",
            "full_name": "Duplicate Author"
        }

        liker_data = {
            "email": "dup_liker@example.com",
            "username": "dup_liker",
            "password": "password123",
            "full_name": "Duplicate Liker"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=liker_data)

        # Create post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post for duplicate like test", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Like the post
        login_liker = await async_test_client.post("/api/v1/auth/login", json={
            "email": liker_data["email"],
            "password": liker_data["password"]
        })

        token_liker = login_liker.json()["access_token"]
        headers_liker = {"Authorization": f"Bearer {token_liker}"}

        await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/like", headers=headers_liker)

        # Try to like again
        response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/like", headers=headers_liker)

        assert_error_response(response, 400, "ALREADY_LIKED")


class TestComments(AsyncTestCase):
    """Test comment functionality."""

    async def test_create_comment(self, async_test_client: AsyncClient):
        """Test creating a comment on a post."""
        # Create two users
        author_data = {
            "email": "comment_author@example.com",
            "username": "comment_author",
            "password": "password123",
            "full_name": "Comment Author"
        }

        commenter_data = {
            "email": "commenter@example.com",
            "username": "commenter",
            "password": "password123",
            "full_name": "Commenter"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=commenter_data)

        # Author creates post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post for commenting", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Commenter creates comment
        login_commenter = await async_test_client.post("/api/v1/auth/login", json={
            "email": commenter_data["email"],
            "password": commenter_data["password"]
        })

        token_commenter = login_commenter.json()["access_token"]
        headers_commenter = {"Authorization": f"Bearer {token_commenter}"}

        comment_data = {
            "content": "This is a great post!",
            "parent_id": None  # Top-level comment
        }

        response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/comments", json=comment_data, headers=headers_commenter)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["content"] == comment_data["content"]
        assert data["author"]["username"] == commenter_data["username"]
        assert data["likes"] == 0

    async def test_reply_to_comment(self, async_test_client: AsyncClient):
        """Test replying to a comment."""
        # Create users and post with comment
        author_data = {
            "email": "reply_author@example.com",
            "username": "reply_author",
            "password": "password123",
            "full_name": "Reply Author"
        }

        commenter_data = {
            "email": "reply_commenter@example.com",
            "username": "reply_commenter",
            "password": "password123",
            "full_name": "Reply Commenter"
        }

        replier_data = {
            "email": "replier@example.com",
            "username": "replier",
            "password": "password123",
            "full_name": "Replier"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=commenter_data)
        await async_test_client.post("/api/v1/auth/register", json=replier_data)

        # Create post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post for reply test", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Create comment
        login_commenter = await async_test_client.post("/api/v1/auth/login", json={
            "email": commenter_data["email"],
            "password": commenter_data["password"]
        })

        token_commenter = login_commenter.json()["access_token"]
        headers_commenter = {"Authorization": f"Bearer {token_commenter}"}

        comment_data = {"content": "Original comment", "parent_id": None}
        comment_response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/comments", json=comment_data, headers=headers_commenter)
        comment_id = comment_response.json()["id"]

        # Reply to comment
        login_replier = await async_test_client.post("/api/v1/auth/login", json={
            "email": replier_data["email"],
            "password": replier_data["password"]
        })

        token_replier = login_replier.json()["access_token"]
        headers_replier = {"Authorization": f"Bearer {token_replier}"}

        reply_data = {
            "content": "This is a reply to the comment!",
            "parent_id": comment_id
        }

        response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/comments", json=reply_data, headers=headers_replier)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["content"] == reply_data["content"]
        assert data["parent_id"] == comment_id
        assert data["author"]["username"] == replier_data["username"]

    async def test_get_post_comments(self, async_test_client: AsyncClient):
        """Test getting comments for a post."""
        # Create users and post with comments
        author_data = {
            "email": "comments_author@example.com",
            "username": "comments_author",
            "password": "password123",
            "full_name": "Comments Author"
        }

        commenter1_data = {
            "email": "commenter1@example.com",
            "username": "commenter1",
            "password": "password123",
            "full_name": "Commenter One"
        }

        commenter2_data = {
            "email": "commenter2@example.com",
            "username": "commenter2",
            "password": "password123",
            "full_name": "Commenter Two"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=commenter1_data)
        await async_test_client.post("/api/v1/auth/register", json=commenter2_data)

        # Create post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post with multiple comments", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Create multiple comments
        for i, commenter in enumerate([commenter1_data, commenter2_data]):
            login_commenter = await async_test_client.post("/api/v1/auth/login", json={
                "email": commenter["email"],
                "password": commenter["password"]
            })

            token_commenter = login_commenter.json()["access_token"]
            headers_commenter = {"Authorization": f"Bearer {token_commenter}"}

            comment_data = {"content": f"Comment number {i+1}", "parent_id": None}
            await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/comments", json=comment_data, headers=headers_commenter)

        # Get comments
        response = await async_test_client.get(f"/api/v1/feeds/posts/{post_id}/comments")

        assert_successful_response(response, 200)
        data = response.json()

        assert len(data["items"]) == 2
        assert_pagination_response(response, 2)

    async def test_like_comment(self, async_test_client: AsyncClient):
        """Test liking a comment."""
        # Create users and post with comment
        author_data = {
            "email": "like_comment_author@example.com",
            "username": "like_comment_author",
            "password": "password123",
            "full_name": "Like Comment Author"
        }

        commenter_data = {
            "email": "like_commenter@example.com",
            "username": "like_commenter",
            "password": "password123",
            "full_name": "Like Commenter"
        }

        liker_data = {
            "email": "like_comment_liker@example.com",
            "username": "like_comment_liker",
            "password": "password123",
            "full_name": "Like Comment Liker"
        }

        await async_test_client.post("/api/v1/auth/register", json=author_data)
        await async_test_client.post("/api/v1/auth/register", json=commenter_data)
        await async_test_client.post("/api/v1/auth/register", json=liker_data)

        # Create post
        login_author = await async_test_client.post("/api/v1/auth/login", json={
            "email": author_data["email"],
            "password": author_data["password"]
        })

        token_author = login_author.json()["access_token"]
        headers_author = {"Authorization": f"Bearer {token_author}"}

        post_data = {"content": "Post for comment liking", "is_public": True}
        create_response = await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers_author)
        post_id = create_response.json()["id"]

        # Create comment
        login_commenter = await async_test_client.post("/api/v1/auth/login", json={
            "email": commenter_data["email"],
            "password": commenter_data["password"]
        })

        token_commenter = login_commenter.json()["access_token"]
        headers_commenter = {"Authorization": f"Bearer {token_commenter}"}

        comment_data = {"content": "Comment to be liked", "parent_id": None}
        comment_response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/comments", json=comment_data, headers=headers_commenter)
        comment_id = comment_response.json()["id"]

        # Like the comment
        login_liker = await async_test_client.post("/api/v1/auth/login", json={
            "email": liker_data["email"],
            "password": liker_data["password"]
        })

        token_liker = login_liker.json()["access_token"]
        headers_liker = {"Authorization": f"Bearer {token_liker}"}

        response = await async_test_client.post(f"/api/v1/feeds/posts/{post_id}/comments/{comment_id}/like", headers=headers_liker)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["liked"] == True


class TestSocialFeatures(AsyncTestCase):
    """Test social features like following users."""

    async def test_follow_user(self, async_test_client: AsyncClient):
        """Test following another user."""
        # Create two users
        follower_data = {
            "email": "follower@example.com",
            "username": "follower",
            "password": "password123",
            "full_name": "Follower"
        }

        followed_data = {
            "email": "followed@example.com",
            "username": "followed",
            "password": "password123",
            "full_name": "Followed User"
        }

        await async_test_client.post("/api/v1/auth/register", json=follower_data)
        await async_test_client.post("/api/v1/auth/register", json=followed_data)

        # Follower follows the other user
        login_follower = await async_test_client.post("/api/v1/auth/login", json={
            "email": follower_data["email"],
            "password": follower_data["password"]
        })

        token_follower = login_follower.json()["access_token"]
        headers_follower = {"Authorization": f"Bearer {token_follower}"}

        response = await async_test_client.post(f"/api/v1/feeds/users/{followed_data['username']}/follow", headers=headers_follower)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["following"] == True

    async def test_unfollow_user(self, async_test_client: AsyncClient):
        """Test unfollowing a user."""
        # Create users and follow relationship
        follower_data = {
            "email": "unfollower@example.com",
            "username": "unfollower",
            "password": "password123",
            "full_name": "Unfollower"
        }

        followed_data = {
            "email": "unfollowed@example.com",
            "username": "unfollowed",
            "password": "password123",
            "full_name": "Unfollowed User"
        }

        await async_test_client.post("/api/v1/auth/register", json=follower_data)
        await async_test_client.post("/api/v1/auth/register", json=followed_data)

        # Follow first
        login_follower = await async_test_client.post("/api/v1/auth/login", json={
            "email": follower_data["email"],
            "password": follower_data["password"]
        })

        token_follower = login_follower.json()["access_token"]
        headers_follower = {"Authorization": f"Bearer {token_follower}"}

        await async_test_client.post(f"/api/v1/feeds/users/{followed_data['username']}/follow", headers=headers_follower)

        # Then unfollow
        response = await async_test_client.delete(f"/api/v1/feeds/users/{followed_data['username']}/follow", headers=headers_follower)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["following"] == False

    async def test_get_followers(self, async_test_client: AsyncClient):
        """Test getting list of followers."""
        # Create users and follow relationships
        followed_data = {
            "email": "followed_main@example.com",
            "username": "followed_main",
            "password": "password123",
            "full_name": "Followed Main"
        }

        follower1_data = {
            "email": "follower1@example.com",
            "username": "follower1",
            "password": "password123",
            "full_name": "Follower One"
        }

        follower2_data = {
            "email": "follower2@example.com",
            "username": "follower2",
            "password": "password123",
            "full_name": "Follower Two"
        }

        await async_test_client.post("/api/v1/auth/register", json=followed_data)
        await async_test_client.post("/api/v1/auth/register", json=follower1_data)
        await async_test_client.post("/api/v1/auth/register", json=follower2_data)

        # Both followers follow the main user
        for follower in [follower1_data, follower2_data]:
            login_follower = await async_test_client.post("/api/v1/auth/login", json={
                "email": follower["email"],
                "password": follower["password"]
            })

            token_follower = login_follower.json()["access_token"]
            headers_follower = {"Authorization": f"Bearer {token_follower}"}

            await async_test_client.post(f"/api/v1/feeds/users/{followed_data['username']}/follow", headers=headers_follower)

        # Get followers
        response = await async_test_client.get(f"/api/v1/feeds/users/{followed_data['username']}/followers")

        assert_successful_response(response, 200)
        data = response.json()

        assert len(data["items"]) == 2
        assert_pagination_response(response, 2)

    async def test_get_following(self, async_test_client: AsyncClient):
        """Test getting list of users being followed."""
        # Create users and follow relationships
        follower_data = {
            "email": "main_follower@example.com",
            "username": "main_follower",
            "password": "password123",
            "full_name": "Main Follower"
        }

        followed1_data = {
            "email": "followed1@example.com",
            "username": "followed1",
            "password": "password123",
            "full_name": "Followed One"
        }

        followed2_data = {
            "email": "followed2@example.com",
            "username": "followed2",
            "password": "password123",
            "full_name": "Followed Two"
        }

        await async_test_client.post("/api/v1/auth/register", json=follower_data)
        await async_test_client.post("/api/v1/auth/register", json=followed1_data)
        await async_test_client.post("/api/v1/feeds/register", json=followed2_data)

        # Follower follows both users
        login_follower = await async_test_client.post("/api/v1/auth/login", json={
            "email": follower_data["email"],
            "password": follower_data["password"]
        })

        token_follower = login_follower.json()["access_token"]
        headers_follower = {"Authorization": f"Bearer {token_follower}"}

        for followed in [followed1_data, followed2_data]:
            await async_test_client.post(f"/api/v1/feeds/users/{followed['username']}/follow", headers=headers_follower)

        # Get following
        response = await async_test_client.get(f"/api/v1/feeds/users/{follower_data['username']}/following", headers=headers_follower)

        assert_successful_response(response, 200)
        data = response.json()

        assert len(data["items"]) == 2
        assert_pagination_response(response, 2)
