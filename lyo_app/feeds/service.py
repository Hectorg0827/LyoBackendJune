"""
Feeds service implementation.
Handles posts, comments, reactions, and social feed operations.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.feeds.models import (
    Post, Comment, PostReaction, CommentReaction, UserFollow, FeedItem,
    PostType, ReactionType, UserInteraction, InteractionType
)
from lyo_app.feeds.schemas import (
    PostCreate, PostUpdate, CommentCreate, CommentUpdate,
    PostReactionCreate, CommentReactionCreate, UserFollowCreate
)
from lyo_app.feeds.services_ranking import rank_posts_for_user
from lyo_app.stack import crud as stack_crud
from lyo_app.stack.models import StackItemType
from lyo_app.stack.schemas import StackItemCreate
from lyo_app.tasks import video_tasks


class FeedsService:
    """Service class for social feeds and interactions."""

    async def create_post(
        self, 
        db: AsyncSession, 
        author_id: int, 
        post_data: PostCreate
    ) -> Post:
        """
        Create a new post.
        
        Args:
            db: Database session
            author_id: ID of the user creating the post
            post_data: Post creation data
            
        Returns:
            Created post instance
        """
        db_post = Post(
            content=post_data.content,
            post_type=post_data.post_type,
            image_url=post_data.image_url,
            video_url=post_data.video_url,
            link_url=post_data.link_url,
            link_title=post_data.link_title,
            link_description=post_data.link_description,
            author_id=author_id,
            is_public=post_data.is_public,
            course_id=post_data.course_id,
            lesson_id=post_data.lesson_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_post)
        await db.commit()
        await db.refresh(db_post)
        
        # Create feed items for followers (fan-out approach)
        await self._fan_out_post_to_followers(db, db_post)
        
        return db_post

    async def get_post_by_id(self, db: AsyncSession, post_id: int) -> Optional[Post]:
        """
        Get post by ID with comments and reactions.
        
        Args:
            db: Database session
            post_id: Post ID to search for
            
        Returns:
            Post instance if found, None otherwise
        """
        result = await db.execute(
            select(Post)
            .options(
                selectinload(Post.comments),
                selectinload(Post.reactions)
            )
            .where(Post.id == post_id)
        )
        return result.scalar_one_or_none()

    async def get_posts_by_author(
        self, 
        db: AsyncSession, 
        author_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> List[Post]:
        """
        Get posts by author ID.
        
        Args:
            db: Database session
            author_id: Author user ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of posts by the author
        """
        result = await db.execute(
            select(Post)
            .where(Post.author_id == author_id)
            .order_by(desc(Post.created_at))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_public_feed(
        self, 
        db: AsyncSession,
        current_user_id: int,
        page: int = 1,
        per_page: int = 20,
        course_id: Optional[int] = None,
        lesson_id: Optional[int] = None
    ) -> dict:
        """
        Get public posts for discovery feed with pagination.
        
        Args:
            db: Database session
            current_user_id: Current user ID for permission checks
            page: Page number (1-based)
            per_page: Maximum number of records to return
            course_id: Optional course context
            lesson_id: Optional lesson context
            
        Returns:
            Paginated public feed response
        """
        offset = (page - 1) * per_page
        
        # Build query
        query = select(Post).where(Post.is_public == True)
        
        if lesson_id:
            query = query.where(Post.lesson_id == lesson_id)
        elif course_id:
            query = query.where(Post.course_id == course_id)
            
        # Get public posts
        result = await db.execute(
            query
            .order_by(desc(Post.created_at))
            .offset(offset)
            .limit(per_page)
        )
        posts = result.scalars().all()
        
        # Apply AI ranking (Context-Aware)
        # We pass the DB and user_id so the ranking service can look up the user's context
        posts = await rank_posts_for_user(
            list(posts), 
            db=db, 
            user_id=current_user_id, 
            context={"course_id": course_id, "lesson_id": lesson_id}
        )
        
        # Get total count
        count_query = select(func.count(Post.id)).where(Post.is_public == True)
        if lesson_id:
            count_query = count_query.where(Post.lesson_id == lesson_id)
        elif course_id:
            count_query = count_query.where(Post.course_id == course_id)
            
        count_result = await db.execute(count_query)
        total = count_result.scalar()
        
        # Convert to PostRead format
        posts_data = []
        for post in posts:
            # Get user's reaction
            user_reaction_result = await db.execute(
                select(PostReaction.reaction_type).where(
                    and_(
                        PostReaction.post_id == post.id,
                        PostReaction.user_id == current_user_id
                    )
                )
            )
            user_reaction = user_reaction_result.scalar_one_or_none()
            
            # Get comment count
            comment_count_result = await db.execute(
                select(func.count(Comment.id)).where(Comment.post_id == post.id)
            )
            comment_count = comment_count_result.scalar()
            
            # Get reaction count
            reaction_count_result = await db.execute(
                select(func.count(PostReaction.id)).where(PostReaction.post_id == post.id)
            )
            reaction_count = reaction_count_result.scalar()
            
            post_data = {
                "id": post.id,
                "content": post.content,
                "post_type": post.post_type,
                "image_url": post.image_url,
                "video_url": post.video_url,
                "link_url": post.link_url,
                "link_title": post.link_title,
                "link_description": post.link_description,
                "is_public": post.is_public,
                "is_pinned": post.is_pinned,
                "course_id": post.course_id,
                "lesson_id": post.lesson_id,
                "author_id": post.author_id,
                "created_at": post.created_at,
                "updated_at": post.updated_at,
                "comment_count": comment_count or 0,
                "reaction_count": reaction_count or 0,
                "user_reaction": user_reaction,
            }
            posts_data.append(post_data)
        
        return {
            "posts": posts_data,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "has_next": total > page * per_page,
        }

    async def create_comment(
        self, 
        db: AsyncSession, 
        author_id: int, 
        comment_data: CommentCreate
    ) -> Comment:
        """
        Create a new comment.
        
        Args:
            db: Database session
            author_id: ID of the user creating the comment
            comment_data: Comment creation data
            
        Returns:
            Created comment instance
            
        Raises:
            ValueError: If post not found or parent comment invalid
        """
        # Verify post exists
        post = await self.get_post_by_id(db, comment_data.post_id)
        if not post:
            raise ValueError("Post not found")
        
        # Verify parent comment exists if specified
        if comment_data.parent_comment_id:
            parent_result = await db.execute(
                select(Comment).where(Comment.id == comment_data.parent_comment_id)
            )
            parent_comment = parent_result.scalar_one_or_none()
            if not parent_comment:
                raise ValueError("Parent comment not found")
            if parent_comment.post_id != comment_data.post_id:
                raise ValueError("Parent comment belongs to different post")
        
        db_comment = Comment(
            content=comment_data.content,
            post_id=comment_data.post_id,
            author_id=author_id,
            parent_comment_id=comment_data.parent_comment_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_comment)
        await db.commit()
        await db.refresh(db_comment)
        
        return db_comment

    async def get_comments_by_post(
        self, 
        db: AsyncSession, 
        post_id: int
    ) -> List[Comment]:
        """
        Get all comments for a post, ordered by creation time.
        
        Args:
            db: Database session
            post_id: Post ID
            
        Returns:
            List of comments
        """
        result = await db.execute(
            select(Comment)
            .where(Comment.post_id == post_id)
            .order_by(Comment.created_at)
        )
        return list(result.scalars().all())

    async def react_to_post(
        self, 
        db: AsyncSession, 
        user_id: int, 
        reaction_data: PostReactionCreate
    ) -> PostReaction:
        """
        React to a post (or update existing reaction).
        
        Args:
            db: Database session
            user_id: ID of the user reacting
            reaction_data: Reaction data
            
        Returns:
            Created or updated reaction instance
            
        Raises:
            ValueError: If post not found
        """
        # Verify post exists
        post = await self.get_post_by_id(db, reaction_data.post_id)
        if not post:
            raise ValueError("Post not found")
        
        # Check if user already reacted to this post
        existing_reaction_result = await db.execute(
            select(PostReaction).where(
                and_(
                    PostReaction.post_id == reaction_data.post_id,
                    PostReaction.user_id == user_id
                )
            )
        )
        existing_reaction = existing_reaction_result.scalar_one_or_none()
        
        if existing_reaction:
            # Update existing reaction
            existing_reaction.reaction_type = reaction_data.reaction_type
            existing_reaction.created_at = datetime.utcnow()  # Update timestamp
            await db.commit()
            await db.refresh(existing_reaction)
            return existing_reaction
        else:
            # Create new reaction
            db_reaction = PostReaction(
                post_id=reaction_data.post_id,
                user_id=user_id,
                reaction_type=reaction_data.reaction_type,
                created_at=datetime.utcnow(),
            )
            
            db.add(db_reaction)
            await db.commit()
            await db.refresh(db_reaction)
            
            return db_reaction

    async def react_to_comment(
        self, 
        db: AsyncSession, 
        user_id: int, 
        reaction_data: CommentReactionCreate
    ) -> CommentReaction:
        """
        React to a comment (or update existing reaction).
        
        Args:
            db: Database session
            user_id: ID of the user reacting
            reaction_data: Reaction data
            
        Returns:
            Created or updated reaction instance
            
        Raises:
            ValueError: If comment not found
        """
        # Verify comment exists
        comment_result = await db.execute(
            select(Comment).where(Comment.id == reaction_data.comment_id)
        )
        comment = comment_result.scalar_one_or_none()
        if not comment:
            raise ValueError("Comment not found")
        
        # Check if user already reacted to this comment
        existing_reaction_result = await db.execute(
            select(CommentReaction).where(
                and_(
                    CommentReaction.comment_id == reaction_data.comment_id,
                    CommentReaction.user_id == user_id
                )
            )
        )
        existing_reaction = existing_reaction_result.scalar_one_or_none()
        
        if existing_reaction:
            # Update existing reaction
            existing_reaction.reaction_type = reaction_data.reaction_type
            existing_reaction.created_at = datetime.utcnow()
            await db.commit()
            await db.refresh(existing_reaction)
            return existing_reaction
        else:
            # Create new reaction
            db_reaction = CommentReaction(
                comment_id=reaction_data.comment_id,
                user_id=user_id,
                reaction_type=reaction_data.reaction_type,
                created_at=datetime.utcnow(),
            )
            
            db.add(db_reaction)
            await db.commit()
            await db.refresh(db_reaction)
            
            return db_reaction

    async def follow_user(
        self, 
        db: AsyncSession, 
        follower_id: int, 
        follow_data: UserFollowCreate
    ) -> UserFollow:
        """
        Follow another user.
        
        Args:
            db: Database session
            follower_id: ID of the user doing the following
            follow_data: Follow data
            
        Returns:
            Created follow relationship
            
        Raises:
            ValueError: If trying to follow self or already following
        """
        if follower_id == follow_data.following_id:
            raise ValueError("Cannot follow yourself")
        
        # Check if already following
        existing_follow_result = await db.execute(
            select(UserFollow).where(
                and_(
                    UserFollow.follower_id == follower_id,
                    UserFollow.following_id == follow_data.following_id
                )
            )
        )
        existing_follow = existing_follow_result.scalar_one_or_none()
        
        if existing_follow:
            raise ValueError("Already following this user")
        
        db_follow = UserFollow(
            follower_id=follower_id,
            following_id=follow_data.following_id,
            created_at=datetime.utcnow(),
        )
        
        db.add(db_follow)
        await db.commit()
        await db.refresh(db_follow)
        
        return db_follow

    async def unfollow_user(
        self, 
        db: AsyncSession, 
        follower_id: int, 
        following_id: int
    ) -> bool:
        """
        Unfollow a user.
        
        Args:
            db: Database session
            follower_id: ID of the user doing the unfollowing
            following_id: ID of the user to unfollow
            
        Returns:
            True if unfollowed, False if not following
        """
        follow_result = await db.execute(
            select(UserFollow).where(
                and_(
                    UserFollow.follower_id == follower_id,
                    UserFollow.following_id == following_id
                )
            )
        )
        follow = follow_result.scalar_one_or_none()
        
        if follow:
            await db.delete(follow)
            await db.commit()
            return True
        
        return False

    async def get_user_feed(
        self, 
        db: AsyncSession, 
        user_id: int,
        page: int = 1,
        per_page: int = 20
    ) -> dict:
        """
        Get personalized feed for a user with pagination.
        Returns posts from followed users and own posts.
        
        Args:
            db: Database session
            user_id: User ID
            page: Page number (1-based)
            per_page: Maximum number of records to return
            
        Returns:
            Paginated feed response
        """
        offset = (page - 1) * per_page
        
        # Get followed users
        followed_users_result = await db.execute(
            select(UserFollow.following_id).where(UserFollow.follower_id == user_id)
        )
        followed_user_ids = [row[0] for row in followed_users_result.all()]
        
        # Include the user's own posts
        author_ids = followed_user_ids + [user_id]
        
        # Get posts from followed users and self
        result = await db.execute(
            select(Post)
            .where(
                and_(
                    Post.author_id.in_(author_ids),
                    Post.is_public == True
                )
            )
            .order_by(desc(Post.created_at))
            .offset(offset)
            .limit(per_page)
        )
        posts = result.scalars().all()
        
        # Get total count
        count_result = await db.execute(
            select(func.count(Post.id))
            .where(
                and_(
                    Post.author_id.in_(author_ids),
                    Post.is_public == True
                )
            )
        )
        total = count_result.scalar()
        
        # Convert to PostRead format
        posts_data = []
        for post in posts:
            # Get user's reaction
            user_reaction_result = await db.execute(
                select(PostReaction.reaction_type).where(
                    and_(
                        PostReaction.post_id == post.id,
                        PostReaction.user_id == user_id
                    )
                )
            )
            user_reaction = user_reaction_result.scalar_one_or_none()
            
            # Get comment count
            comment_count_result = await db.execute(
                select(func.count(Comment.id)).where(Comment.post_id == post.id)
            )
            comment_count = comment_count_result.scalar()
            
            # Get reaction count
            reaction_count_result = await db.execute(
                select(func.count(PostReaction.id)).where(PostReaction.post_id == post.id)
            )
            reaction_count = reaction_count_result.scalar()
            
            post_data = {
                "id": post.id,
                "content": post.content,
                "post_type": post.post_type,
                "image_url": post.image_url,
                "video_url": post.video_url,
                "link_url": post.link_url,
                "link_title": post.link_title,
                "link_description": post.link_description,
                "is_public": post.is_public,
                "is_pinned": post.is_pinned,
                "course_id": post.course_id,
                "lesson_id": post.lesson_id,
                "author_id": post.author_id,
                "created_at": post.created_at,
                "updated_at": post.updated_at,
                "comment_count": comment_count or 0,
                "reaction_count": reaction_count or 0,
                "user_reaction": user_reaction,
            }
            posts_data.append(post_data)
        
        return {
            "posts": posts_data,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "has_next": total > page * per_page,
        }

    async def _fan_out_post_to_followers(self, db: AsyncSession, post: Post) -> None:
        """
        Create feed items for all followers of the post author.
        This implements the "fan-out on write" approach for feed generation.
        
        Args:
            db: Database session
            post: The newly created post
        """
        if not post.is_public:
            return  # Don't fan out private posts
        
        # Get all followers of the post author
        followers_result = await db.execute(
            select(UserFollow.follower_id).where(UserFollow.following_id == post.author_id)
        )
        follower_ids = [row[0] for row in followers_result.all()]
        
        # Create feed items for each follower
        feed_items = []
        for follower_id in follower_ids:
            feed_item = FeedItem(
                user_id=follower_id,
                post_id=post.id,
                score=1.0,  # Basic scoring, can be enhanced with ML later
                created_at=datetime.utcnow(),
            )
            feed_items.append(feed_item)
        
        if feed_items:
            db.add_all(feed_items)
            await db.commit()

    async def get_user_statistics(self, db: AsyncSession, user_id: int) -> dict:
        """
        Get social statistics for a user.
        
        Args:
            db: Database session
            user_id: User ID
            
        Returns:
            Dictionary with user statistics
        """
        # Count posts
        posts_count_result = await db.execute(
            select(func.count(Post.id)).where(Post.author_id == user_id)
        )
        posts_count = posts_count_result.scalar()
        
        # Count followers
        followers_count_result = await db.execute(
            select(func.count(UserFollow.id)).where(UserFollow.following_id == user_id)
        )
        followers_count = followers_count_result.scalar()
        
        # Count following
        following_count_result = await db.execute(
            select(func.count(UserFollow.id)).where(UserFollow.follower_id == user_id)
        )
        following_count = following_count_result.scalar()
        
        # Count total reactions received
        reactions_count_result = await db.execute(
            select(func.count(PostReaction.id))
            .join(Post, Post.id == PostReaction.post_id)
            .where(Post.author_id == user_id)
        )
        total_reactions = reactions_count_result.scalar()
        
        return {
            "posts_count": posts_count or 0,
            "followers_count": followers_count or 0,
            "following_count": following_count or 0,
            "total_reactions_received": total_reactions or 0,
        }

    async def get_post_with_details(
        self, 
        db: AsyncSession, 
        post_id: int, 
        current_user_id: int
    ) -> Optional[dict]:
        """
        Get a post with its comments and reactions.
        
        Args:
            db: Database session
            post_id: Post ID to retrieve
            current_user_id: Current user ID for permission checks
            
        Returns:
            Post with comments and reactions, or None if not found
        """
        # Get the post
        post = await self.get_post_by_id(db, post_id)
        if not post:
            return None
        
        # Get comments
        comments = await self.get_comments_by_post(db, post_id)
        
        # Get post reactions
        post_reactions_result = await db.execute(
            select(PostReaction).where(PostReaction.post_id == post_id)
        )
        post_reactions = post_reactions_result.scalars().all()
        
        # Get user's reaction to the post
        user_reaction_result = await db.execute(
            select(PostReaction.reaction_type).where(
                and_(
                    PostReaction.post_id == post_id,
                    PostReaction.user_id == current_user_id
                )
            )
        )
        user_reaction = user_reaction_result.scalar_one_or_none()
        
        # Build response
        post_dict = {
            "id": post.id,
            "content": post.content,
            "post_type": post.post_type,
            "image_url": post.image_url,
            "video_url": post.video_url,
            "link_url": post.link_url,
            "link_title": post.link_title,
            "link_description": post.link_description,
            "is_public": post.is_public,
            "is_pinned": post.is_pinned,
            "course_id": post.course_id,
            "lesson_id": post.lesson_id,
            "author_id": post.author_id,
            "created_at": post.created_at,
            "updated_at": post.updated_at,
            "comment_count": len(comments),
            "reaction_count": len(post_reactions),
            "user_reaction": user_reaction,
            "comments": [
                {
                    "id": comment.id,
                    "content": comment.content,
                    "post_id": comment.post_id,
                    "author_id": comment.author_id,
                    "parent_comment_id": comment.parent_comment_id,
                    "created_at": comment.created_at,
                    "updated_at": comment.updated_at,
                }
                for comment in comments
            ],
            "reactions": [
                {
                    "id": reaction.id,
                    "user_id": reaction.user_id,
                    "reaction_type": reaction.reaction_type,
                    "created_at": reaction.created_at,
                }
                for reaction in post_reactions
            ]
        }
        
        return post_dict

    async def update_post(
        self, 
        db: AsyncSession, 
        post_id: int, 
        user_id: int, 
        post_data: PostUpdate
    ) -> Optional[Post]:
        """
        Update a post.
        
        Args:
            db: Database session
            post_id: Post ID to update
            user_id: ID of the user attempting to update
            post_data: Updated post data
            
        Returns:
            Updated post instance or None if not found
            
        Raises:
            PermissionError: If user is not the author
        """
        # Get the post
        post = await self.get_post_by_id(db, post_id)
        if not post:
            return None
            
        # Check ownership
        if post.author_id != user_id:
            raise PermissionError("Only the author can update this post")
        
        # Update fields
        if post_data.content is not None:
            post.content = post_data.content
        if post_data.is_public is not None:
            post.is_public = post_data.is_public
        if post_data.is_pinned is not None:
            post.is_pinned = post_data.is_pinned
        
        post.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(post)
        
        return post

    async def delete_post(
        self, 
        db: AsyncSession, 
        post_id: int, 
        user_id: int
    ) -> bool:
        """
        Delete a post.
        
        Args:
            db: Database session
            post_id: Post ID to delete
            user_id: ID of the user attempting to delete
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            PermissionError: If user is not the author
        """
        # Get the post
        post = await self.get_post_by_id(db, post_id)
        if not post:
            return False
            
        # Check ownership
        if post.author_id != user_id:
            raise PermissionError("Only the author can delete this post")
        
        await db.delete(post)
        await db.commit()
        
        return True

    async def update_comment(
        self, 
        db: AsyncSession, 
        comment_id: int, 
        user_id: int, 
        comment_data: CommentUpdate
    ) -> Optional[Comment]:
        """
        Update a comment.
        
        Args:
            db: Database session
            comment_id: Comment ID to update
            user_id: ID of the user attempting to update
            comment_data: Updated comment data
            
        Returns:
            Updated comment instance or None if not found
            
        Raises:
            PermissionError: If user is not the author
        """
        # Get the comment
        result = await db.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            return None
            
        # Check ownership
        if comment.author_id != user_id:
            raise PermissionError("Only the author can update this comment")
        
        # Update content
        comment.content = comment_data.content
        comment.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(comment)
        
        return comment

    async def delete_comment(
        self, 
        db: AsyncSession, 
        comment_id: int, 
        user_id: int
    ) -> bool:
        """
        Delete a comment.
        
        Args:
            db: Database session
            comment_id: Comment ID to delete
            user_id: ID of the user attempting to delete
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            PermissionError: If user is not the author
        """
        # Get the comment
        result = await db.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        comment = result.scalar_one_or_none()
        
        if not comment:
            return False
            
        # Check ownership
        if comment.author_id != user_id:
            raise PermissionError("Only the author can delete this comment")
        
        await db.delete(comment)
        await db.commit()
        
        return True

    async def remove_post_reaction(
        self, 
        db: AsyncSession, 
        user_id: int, 
        post_id: int
    ) -> None:
        """
        Remove a user's reaction from a post.
        
        Args:
            db: Database session
            user_id: User ID
            post_id: Post ID
        """
        result = await db.execute(
            select(PostReaction).where(
                and_(
                    PostReaction.user_id == user_id,
                    PostReaction.post_id == post_id
                )
            )
        )
        reaction = result.scalar_one_or_none()
        
        if reaction:
            await db.delete(reaction)
            await db.commit()

    async def remove_comment_reaction(
        self, 
        db: AsyncSession, 
        user_id: int, 
        comment_id: int
    ) -> None:
        """
        Remove a user's reaction from a comment.
        
        Args:
            db: Database session
            user_id: User ID
            comment_id: Comment ID
        """
        result = await db.execute(
            select(CommentReaction).where(
                and_(
                    CommentReaction.user_id == user_id,
                    CommentReaction.comment_id == comment_id
                )
            )
        )
        reaction = result.scalar_one_or_none()
        
        if reaction:
            await db.delete(reaction)
            await db.commit()

    async def get_user_posts(
        self, 
        db: AsyncSession, 
        user_id: int, 
        current_user_id: int,
        page: int = 1, 
        per_page: int = 20
    ) -> dict:
        """
        Get posts by a specific user with pagination.
        
        Args:
            db: Database session
            user_id: User ID whose posts to retrieve
            current_user_id: Current user ID for permission checks
            page: Page number (1-based)
            per_page: Number of items per page
            
        Returns:
            Paginated posts response
        """
        offset = (page - 1) * per_page
        
        # Get posts
        posts_result = await db.execute(
            select(Post)
            .where(
                and_(
                    Post.author_id == user_id,
                    or_(
                        Post.is_public == True,
                        Post.author_id == current_user_id
                    )
                )
            )
            .order_by(desc(Post.created_at))
            .offset(offset)
            .limit(per_page)
        )
        posts = posts_result.scalars().all()
        
        # Get total count
        count_result = await db.execute(
            select(func.count(Post.id))
            .where(
                and_(
                    Post.author_id == user_id,
                    or_(
                        Post.is_public == True,
                        Post.author_id == current_user_id
                    )
                )
            )
        )
        total = count_result.scalar()
        
        # Convert to PostRead format
        posts_data = []
        for post in posts:
            # Get user's reaction
            user_reaction_result = await db.execute(
                select(PostReaction.reaction_type).where(
                    and_(
                        PostReaction.post_id == post.id,
                        PostReaction.user_id == current_user_id
                    )
                )
            )
            user_reaction = user_reaction_result.scalar_one_or_none()
            
            # Get comment count
            comment_count_result = await db.execute(
                select(func.count(Comment.id)).where(Comment.post_id == post.id)
            )
            comment_count = comment_count_result.scalar()
            
            # Get reaction count
            reaction_count_result = await db.execute(
                select(func.count(PostReaction.id)).where(PostReaction.post_id == post.id)
            )
            reaction_count = reaction_count_result.scalar()
            
            post_data = {
                "id": post.id,
                "content": post.content,
                "post_type": post.post_type,
                "image_url": post.image_url,
                "video_url": post.video_url,
                "link_url": post.link_url,
                "link_title": post.link_title,
                "link_description": post.link_description,
                "is_public": post.is_public,
                "is_pinned": post.is_pinned,
                "course_id": post.course_id,
                "lesson_id": post.lesson_id,
                "author_id": post.author_id,
                "created_at": post.created_at,
                "updated_at": post.updated_at,
                "comment_count": comment_count or 0,
                "reaction_count": reaction_count or 0,
                "user_reaction": user_reaction,
            }
            posts_data.append(post_data)
        
        return {
            "posts": posts_data,
            "total": total or 0,
            "page": page,
            "per_page": per_page,
            "has_next": total > page * per_page,
        }

    async def get_user_stats(self, db: AsyncSession, user_id: int) -> dict:
        """
        Get social statistics for a user.
        
        Args:
            db: Database session
            user_id: User ID to get stats for
            
        Returns:
            User social statistics
        """
        return await self.get_user_statistics(db, user_id)

    async def capture_post(
        self,
        db: AsyncSession,
        user_id: int,
        post_id: int
    ):
        """
        Capture a post to the user's stack.
        
        Args:
            db: Database session
            user_id: User ID capturing the post
            post_id: Post ID to capture
            
        Returns:
            Created StackItem
        """
        # 1. Validate post exists
        post = await self.get_post_by_id(db, post_id)
        if not post:
            raise ValueError("Post not found")
            
        # 2. Create UserInteraction
        interaction = UserInteraction(
            user_id=user_id,
            post_id=post_id,
            interaction_type=InteractionType.CAPTURE,
            created_at=datetime.utcnow()
        )
        db.add(interaction)
        
        # 3. Create StackItem
        # We use the stack crud directly here
        stack_item_in = StackItemCreate(
            type=StackItemType.VIDEO,
            ref_id=str(post_id),
            context_data={
                "source": "discover",
                "course_id": post.course_id,
                "lesson_id": post.lesson_id,
                "original_post_id": post_id
            },
            title=f"Captured Video: {post.id}", # Placeholder title
            content=post.content or ""
        )
        
        stack_item = await stack_crud.create_stack_item(db, user_id, stack_item_in)
        
        # 4. Trigger background task
        # We use .delay() if celery is set up, or just call it if testing/mocking
        try:
            video_tasks.process_captured_video.delay(
                stack_item_id=str(stack_item.id),
                post_id=post_id,
                user_id=str(user_id)
            )
        except Exception as e:
            # Fallback if celery is not running or configured
            print(f"Warning: Could not queue video task: {e}")
            
        return stack_item
