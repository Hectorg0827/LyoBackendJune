"""
Unit tests for the feeds service.
Following TDD principles - tests are written before implementation.
"""

import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.feeds.schemas import PostCreate, CommentCreate, PostReactionCreate, UserFollowCreate
from lyo_app.feeds.service import FeedsService
from lyo_app.feeds.models import Post, Comment, PostType, ReactionType
from lyo_app.models.enhanced import User
from lyo_app.auth.service import AuthService
from lyo_app.auth.schemas import UserCreate


class TestFeedsService:
    """Test cases for FeedsService following TDD principles."""

    @pytest.fixture
    async def feeds_service(self) -> FeedsService:
        """Create a FeedsService instance for testing."""
        return FeedsService()

    @pytest.fixture
    async def auth_service(self) -> AuthService:
        """Create an AuthService instance for testing."""
        return AuthService()

    @pytest.fixture
    async def test_user1(
        self, 
        auth_service: AuthService,
        db_session: AsyncSession
    ) -> User:
        """Create first test user."""
        user_data = UserCreate(
            email="user1@example.com",
            username="user1",
            password="password123",
            confirm_password="password123",
            first_name="Test",
            last_name="User1"
        )
        return await auth_service.register_user(db_session, user_data)

    @pytest.fixture
    async def test_user2(
        self, 
        auth_service: AuthService,
        db_session: AsyncSession
    ) -> User:
        """Create second test user."""
        user_data = UserCreate(
            email="user2@example.com",
            username="user2",
            password="password123",
            confirm_password="password123",
            first_name="Test",
            last_name="User2"
        )
        return await auth_service.register_user(db_session, user_data)

    @pytest.fixture
    def valid_post_data(self) -> PostCreate:
        """Create valid post creation data."""
        return PostCreate(
            content="This is a test post about learning Python!",
            post_type=PostType.TEXT,
            is_public=True
        )

    async def test_create_post_success(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        db_session: AsyncSession
    ):
        """
        Test successful post creation.
        Should create a new post with correct data.
        """
        post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        assert post is not None
        assert post.content == valid_post_data.content
        assert post.post_type == valid_post_data.post_type
        assert post.author_id == test_user1.id
        assert post.is_public is True
        assert post.created_at is not None

    async def test_get_post_by_id(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        db_session: AsyncSession
    ):
        """
        Test retrieving post by ID.
        """
        created_post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        retrieved_post = await feeds_service.get_post_by_id(db_session, created_post.id)
        
        assert retrieved_post is not None
        assert retrieved_post.id == created_post.id
        assert retrieved_post.content == created_post.content

    async def test_get_posts_by_author(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        db_session: AsyncSession
    ):
        """
        Test retrieving posts by author ID.
        """
        # Create two posts for the same author
        post1 = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        post_data_2 = valid_post_data.copy()
        post_data_2.content = "This is my second post!"
        post2 = await feeds_service.create_post(db_session, test_user1.id, post_data_2)
        
        # Retrieve posts by author
        posts = await feeds_service.get_posts_by_author(db_session, test_user1.id)
        
        assert len(posts) == 2
        post_ids = [post.id for post in posts]
        assert post1.id in post_ids
        assert post2.id in post_ids

    async def test_create_comment_success(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test successful comment creation.
        """
        # First create a post
        post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        # Create comment data
        comment_data = CommentCreate(
            content="Great post! Thanks for sharing.",
            post_id=post.id
        )
        
        comment = await feeds_service.create_comment(db_session, test_user2.id, comment_data)
        
        assert comment is not None
        assert comment.content == comment_data.content
        assert comment.post_id == post.id
        assert comment.author_id == test_user2.id
        assert comment.parent_comment_id is None

    async def test_create_comment_reply(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test creating a reply to a comment.
        """
        # Create post and comment
        post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        comment_data = CommentCreate(
            content="Great post!",
            post_id=post.id
        )
        comment = await feeds_service.create_comment(db_session, test_user2.id, comment_data)
        
        # Create reply
        reply_data = CommentCreate(
            content="Thank you!",
            post_id=post.id,
            parent_comment_id=comment.id
        )
        reply = await feeds_service.create_comment(db_session, test_user1.id, reply_data)
        
        assert reply.parent_comment_id == comment.id
        assert reply.post_id == post.id

    async def test_get_comments_by_post(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test retrieving comments by post ID.
        """
        # Create post
        post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        # Create multiple comments
        comment1_data = CommentCreate(
            content="First comment",
            post_id=post.id
        )
        comment2_data = CommentCreate(
            content="Second comment", 
            post_id=post.id
        )
        
        comment1 = await feeds_service.create_comment(db_session, test_user2.id, comment1_data)
        comment2 = await feeds_service.create_comment(db_session, test_user1.id, comment2_data)
        
        # Retrieve comments
        comments = await feeds_service.get_comments_by_post(db_session, post.id)
        
        assert len(comments) == 2
        comment_ids = [comment.id for comment in comments]
        assert comment1.id in comment_ids
        assert comment2.id in comment_ids

    async def test_react_to_post_success(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test successful post reaction.
        """
        # Create post
        post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        # React to post
        reaction_data = PostReactionCreate(
            post_id=post.id,
            reaction_type=ReactionType.LIKE
        )
        reaction = await feeds_service.react_to_post(db_session, test_user2.id, reaction_data)
        
        assert reaction is not None
        assert reaction.post_id == post.id
        assert reaction.user_id == test_user2.id
        assert reaction.reaction_type == ReactionType.LIKE

    async def test_react_to_post_duplicate_updates_reaction(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test that reacting to same post updates existing reaction.
        """
        # Create post
        post = await feeds_service.create_post(db_session, test_user1.id, valid_post_data)
        
        # First reaction
        reaction_data = PostReactionCreate(
            post_id=post.id,
            reaction_type=ReactionType.LIKE
        )
        reaction1 = await feeds_service.react_to_post(db_session, test_user2.id, reaction_data)
        
        # Second reaction (should update existing)
        reaction_data.reaction_type = ReactionType.LOVE
        reaction2 = await feeds_service.react_to_post(db_session, test_user2.id, reaction_data)
        
        assert reaction1.id == reaction2.id  # Same reaction record
        assert reaction2.reaction_type == ReactionType.LOVE

    async def test_follow_user_success(
        self,
        feeds_service: FeedsService,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test successful user following.
        """
        follow_data = UserFollowCreate(following_id=test_user2.id)
        follow = await feeds_service.follow_user(db_session, test_user1.id, follow_data)
        
        assert follow is not None
        assert follow.follower_id == test_user1.id
        assert follow.following_id == test_user2.id

    async def test_follow_user_duplicate_fails(
        self,
        feeds_service: FeedsService,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test that following same user twice fails.
        """
        follow_data = UserFollowCreate(following_id=test_user2.id)
        
        # First follow succeeds
        await feeds_service.follow_user(db_session, test_user1.id, follow_data)
        
        # Second follow should fail
        with pytest.raises(ValueError, match="Already following this user"):
            await feeds_service.follow_user(db_session, test_user1.id, follow_data)

    async def test_follow_self_fails(
        self,
        feeds_service: FeedsService,
        test_user1: User,
        db_session: AsyncSession
    ):
        """
        Test that following yourself fails.
        """
        follow_data = UserFollowCreate(following_id=test_user1.id)
        
        with pytest.raises(ValueError, match="Cannot follow yourself"):
            await feeds_service.follow_user(db_session, test_user1.id, follow_data)

    async def test_get_user_feed(
        self,
        feeds_service: FeedsService,
        valid_post_data: PostCreate,
        test_user1: User,
        test_user2: User,
        db_session: AsyncSession
    ):
        """
        Test getting personalized user feed.
        """
        # User1 follows User2
        follow_data = UserFollowCreate(following_id=test_user2.id)
        await feeds_service.follow_user(db_session, test_user1.id, follow_data)
        
        # User2 creates a post
        post = await feeds_service.create_post(db_session, test_user2.id, valid_post_data)
        
        # User1's feed should contain User2's post
        feed = await feeds_service.get_user_feed(db_session, test_user1.id)
        
        assert len(feed) >= 1
        post_ids = [post.id for post in feed]
        assert post.id in post_ids
