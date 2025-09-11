"""
Polyglot Persistence Strategy Implementation
Advanced data layer abstraction with multiple storage engines
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Union, Tuple, Type, Generic, TypeVar
from datetime import datetime, timedelta
from enum import Enum
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

# SQLAlchemy for PostgreSQL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text, select, update, delete, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

# MongoDB
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection

# InfluxDB for time series
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client import Point

# Redis (already handled by cache manager)
from lyo_app.core.cache_manager import get_cache_manager

import structlog
from lyo_app.core.config import settings

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class StorageEngine(Enum):
    """Available storage engines"""
    POSTGRESQL = "postgresql"
    MONGODB = "mongodb"
    REDIS = "redis"
    INFLUXDB = "influxdb"


class DataCategory(Enum):
    """Data categorization for appropriate storage selection"""
    TRANSACTIONAL = "transactional"        # PostgreSQL - User accounts, orders, core business data
    DOCUMENT = "document"                   # MongoDB - User profiles, content, flexible schemas
    CACHE = "cache"                        # Redis - Sessions, temporary data, computed results
    TIME_SERIES = "time_series"            # InfluxDB - Metrics, analytics, sensor data
    SEARCH = "search"                      # Future: Elasticsearch integration
    BLOB = "blob"                          # Future: S3/Cloud Storage for files


@dataclass
class QueryResult(Generic[T]):
    """Standardized query result wrapper"""
    data: Optional[Union[T, List[T]]]
    count: Optional[int] = None
    metadata: Dict[str, Any] = None
    execution_time: Optional[float] = None
    storage_engine: Optional[StorageEngine] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class QueryOptions:
    """Query execution options"""
    limit: Optional[int] = None
    offset: Optional[int] = 0
    sort: Optional[Dict[str, int]] = None  # {"field": 1/-1} for asc/desc
    include_count: bool = False
    use_cache: bool = True
    cache_ttl: int = 300  # 5 minutes default
    timeout: int = 30     # 30 seconds default


class BaseRepository(ABC, Generic[T]):
    """Abstract base repository for all storage engines"""
    
    def __init__(self, storage_engine: StorageEngine):
        self.storage_engine = storage_engine
    
    @abstractmethod
    async def create(self, data: Dict[str, Any]) -> QueryResult[T]:
        """Create a new record"""
        pass
    
    @abstractmethod
    async def get_by_id(self, record_id: Union[str, int]) -> QueryResult[T]:
        """Get record by ID"""
        pass
    
    @abstractmethod
    async def update(self, record_id: Union[str, int], data: Dict[str, Any]) -> QueryResult[T]:
        """Update record"""
        pass
    
    @abstractmethod
    async def delete(self, record_id: Union[str, int]) -> QueryResult[bool]:
        """Delete record"""
        pass
    
    @abstractmethod
    async def find(
        self,
        filters: Dict[str, Any],
        options: QueryOptions = None
    ) -> QueryResult[List[T]]:
        """Find records with filters"""
        pass


class PostgreSQLRepository(BaseRepository[T]):
    """PostgreSQL repository implementation"""
    
    def __init__(self, table_name: str, model_class: Type[T] = None):
        super().__init__(StorageEngine.POSTGRESQL)
        self.table_name = table_name
        self.model_class = model_class
        self._engine = None
        self._session_maker = None
    
    async def _get_engine(self):
        """Get async engine"""
        if not self._engine:
            database_url = getattr(settings, 'DATABASE_URL', 'postgresql+asyncpg://user:pass@localhost/lyo_app_dev')
            self._engine = create_async_engine(
                database_url,
                echo=False,  # Set to True for query debugging
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            
            self._session_maker = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
        
        return self._engine
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session"""
        await self._get_engine()
        async with self._session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def create(self, data: Dict[str, Any]) -> QueryResult[T]:
        """Create a new record in PostgreSQL"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.get_session() as session:
                # Handle UUID generation
                if 'id' not in data:
                    data['id'] = str(uuid.uuid4())
                
                if 'created_at' not in data:
                    data['created_at'] = datetime.utcnow()
                
                data['updated_at'] = datetime.utcnow()
                
                # Dynamic INSERT using text SQL for flexibility
                columns = ', '.join(data.keys())
                placeholders = ', '.join(f':{key}' for key in data.keys())
                
                query = text(f"""
                    INSERT INTO {self.table_name} ({columns})
                    VALUES ({placeholders})
                    RETURNING *
                """)
                
                result = await session.execute(query, data)
                row = result.fetchone()
                
                if row:
                    record = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                    execution_time = asyncio.get_event_loop().time() - start_time
                    
                    return QueryResult(
                        data=record,
                        execution_time=execution_time,
                        storage_engine=self.storage_engine,
                        metadata={"operation": "create", "table": self.table_name}
                    )
                
                raise Exception("Insert failed - no record returned")
                
        except Exception as e:
            logger.error(f"PostgreSQL create failed: {e}", table=self.table_name)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "create", "table": self.table_name}
            )
    
    async def get_by_id(self, record_id: Union[str, int]) -> QueryResult[T]:
        """Get record by ID from PostgreSQL"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.get_session() as session:
                query = text(f"SELECT * FROM {self.table_name} WHERE id = :id")
                result = await session.execute(query, {"id": record_id})
                row = result.fetchone()
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                if row:
                    record = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                    return QueryResult(
                        data=record,
                        execution_time=execution_time,
                        storage_engine=self.storage_engine,
                        metadata={"operation": "get_by_id", "table": self.table_name}
                    )
                
                return QueryResult(
                    data=None,
                    execution_time=execution_time,
                    storage_engine=self.storage_engine,
                    metadata={"operation": "get_by_id", "table": self.table_name}
                )
                
        except Exception as e:
            logger.error(f"PostgreSQL get_by_id failed: {e}", table=self.table_name, id=record_id)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "get_by_id", "table": self.table_name}
            )
    
    async def update(self, record_id: Union[str, int], data: Dict[str, Any]) -> QueryResult[T]:
        """Update record in PostgreSQL"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.get_session() as session:
                data['updated_at'] = datetime.utcnow()
                
                # Build dynamic UPDATE query
                set_clauses = ', '.join(f'{key} = :{key}' for key in data.keys())
                query = text(f"""
                    UPDATE {self.table_name}
                    SET {set_clauses}
                    WHERE id = :record_id
                    RETURNING *
                """)
                
                params = {**data, 'record_id': record_id}
                result = await session.execute(query, params)
                row = result.fetchone()
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                if row:
                    record = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                    return QueryResult(
                        data=record,
                        execution_time=execution_time,
                        storage_engine=self.storage_engine,
                        metadata={"operation": "update", "table": self.table_name}
                    )
                
                return QueryResult(
                    data=None,
                    execution_time=execution_time,
                    storage_engine=self.storage_engine,
                    metadata={"operation": "update", "table": self.table_name, "not_found": True}
                )
                
        except Exception as e:
            logger.error(f"PostgreSQL update failed: {e}", table=self.table_name, id=record_id)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "update", "table": self.table_name}
            )
    
    async def delete(self, record_id: Union[str, int]) -> QueryResult[bool]:
        """Delete record from PostgreSQL"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.get_session() as session:
                query = text(f"DELETE FROM {self.table_name} WHERE id = :id")
                result = await session.execute(query, {"id": record_id})
                
                execution_time = asyncio.get_event_loop().time() - start_time
                success = result.rowcount > 0
                
                return QueryResult(
                    data=success,
                    execution_time=execution_time,
                    storage_engine=self.storage_engine,
                    metadata={
                        "operation": "delete",
                        "table": self.table_name,
                        "rows_affected": result.rowcount
                    }
                )
                
        except Exception as e:
            logger.error(f"PostgreSQL delete failed: {e}", table=self.table_name, id=record_id)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=False,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "delete", "table": self.table_name}
            )
    
    async def find(
        self,
        filters: Dict[str, Any],
        options: QueryOptions = None
    ) -> QueryResult[List[T]]:
        """Find records with filters in PostgreSQL"""
        if options is None:
            options = QueryOptions()
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with self.get_session() as session:
                # Build WHERE clause
                where_conditions = []
                params = {}
                
                for key, value in filters.items():
                    if isinstance(value, dict):
                        # Handle operators like {"$gt": 100}, {"$in": [1,2,3]}
                        for op, op_value in value.items():
                            if op == "$gt":
                                where_conditions.append(f"{key} > :{key}")
                                params[key] = op_value
                            elif op == "$lt":
                                where_conditions.append(f"{key} < :{key}")
                                params[key] = op_value
                            elif op == "$in":
                                placeholders = ','.join(f':{key}_{i}' for i in range(len(op_value)))
                                where_conditions.append(f"{key} IN ({placeholders})")
                                for i, val in enumerate(op_value):
                                    params[f"{key}_{i}"] = val
                            elif op == "$like":
                                where_conditions.append(f"{key} ILIKE :{key}")
                                params[key] = f"%{op_value}%"
                    else:
                        where_conditions.append(f"{key} = :{key}")
                        params[key] = value
                
                where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
                
                # Build ORDER BY
                order_clause = ""
                if options.sort:
                    order_parts = []
                    for field, direction in options.sort.items():
                        order_parts.append(f"{field} {'ASC' if direction > 0 else 'DESC'}")
                    order_clause = f"ORDER BY {', '.join(order_parts)}"
                
                # Build LIMIT/OFFSET
                limit_clause = ""
                if options.limit:
                    limit_clause = f"LIMIT {options.limit}"
                    if options.offset:
                        limit_clause += f" OFFSET {options.offset}"
                
                # Execute main query
                query = text(f"""
                    SELECT * FROM {self.table_name}
                    WHERE {where_clause}
                    {order_clause}
                    {limit_clause}
                """)
                
                result = await session.execute(query, params)
                rows = result.fetchall()
                
                records = []
                for row in rows:
                    record = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                    records.append(record)
                
                # Get count if requested
                count = None
                if options.include_count:
                    count_query = text(f"""
                        SELECT COUNT(*) FROM {self.table_name}
                        WHERE {where_clause}
                    """)
                    count_result = await session.execute(count_query, params)
                    count = count_result.scalar()
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return QueryResult(
                    data=records,
                    count=count,
                    execution_time=execution_time,
                    storage_engine=self.storage_engine,
                    metadata={
                        "operation": "find",
                        "table": self.table_name,
                        "filters": filters,
                        "options": asdict(options)
                    }
                )
                
        except Exception as e:
            logger.error(f"PostgreSQL find failed: {e}", table=self.table_name, filters=filters)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=[],
                count=0,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "find", "table": self.table_name}
            )


class MongoDBRepository(BaseRepository[T]):
    """MongoDB repository implementation"""
    
    def __init__(self, collection_name: str, database_name: str = "lyo_app"):
        super().__init__(StorageEngine.MONGODB)
        self.collection_name = collection_name
        self.database_name = database_name
        self._client = None
        self._database = None
        self._collection = None
    
    async def _get_collection(self) -> AsyncIOMotorCollection:
        """Get MongoDB collection"""
        if not self._client:
            mongo_url = getattr(settings, 'MONGODB_URL', 'mongodb://localhost:27017')
            self._client = AsyncIOMotorClient(mongo_url)
            self._database = self._client[self.database_name]
            self._collection = self._database[self.collection_name]
        
        return self._collection
    
    async def create(self, data: Dict[str, Any]) -> QueryResult[T]:
        """Create document in MongoDB"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            collection = await self._get_collection()
            
            # Add timestamps
            if 'created_at' not in data:
                data['created_at'] = datetime.utcnow()
            data['updated_at'] = datetime.utcnow()
            
            # MongoDB will auto-generate _id if not provided
            result = await collection.insert_one(data)
            
            if result.inserted_id:
                # Retrieve the inserted document
                inserted_doc = await collection.find_one({"_id": result.inserted_id})
                
                # Convert ObjectId to string for JSON serialization
                if inserted_doc and "_id" in inserted_doc:
                    inserted_doc["id"] = str(inserted_doc["_id"])
                    del inserted_doc["_id"]
                
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return QueryResult(
                    data=inserted_doc,
                    execution_time=execution_time,
                    storage_engine=self.storage_engine,
                    metadata={"operation": "create", "collection": self.collection_name}
                )
            
            raise Exception("Insert failed - no document ID returned")
            
        except Exception as e:
            logger.error(f"MongoDB create failed: {e}", collection=self.collection_name)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "create", "collection": self.collection_name}
            )
    
    async def get_by_id(self, record_id: Union[str, int]) -> QueryResult[T]:
        """Get document by ID from MongoDB"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            from bson import ObjectId
            collection = await self._get_collection()
            
            # Try to convert to ObjectId if it looks like one
            query_id = record_id
            try:
                if isinstance(record_id, str) and len(record_id) == 24:
                    query_id = ObjectId(record_id)
            except:
                pass  # Use as string if ObjectId conversion fails
            
            document = await collection.find_one({"_id": query_id})
            
            if document and "_id" in document:
                document["id"] = str(document["_id"])
                del document["_id"]
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=document,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"operation": "get_by_id", "collection": self.collection_name}
            )
            
        except Exception as e:
            logger.error(f"MongoDB get_by_id failed: {e}", collection=self.collection_name, id=record_id)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "get_by_id", "collection": self.collection_name}
            )
    
    async def update(self, record_id: Union[str, int], data: Dict[str, Any]) -> QueryResult[T]:
        """Update document in MongoDB"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            from bson import ObjectId
            collection = await self._get_collection()
            
            query_id = record_id
            try:
                if isinstance(record_id, str) and len(record_id) == 24:
                    query_id = ObjectId(record_id)
            except:
                pass
            
            data['updated_at'] = datetime.utcnow()
            
            result = await collection.find_one_and_update(
                {"_id": query_id},
                {"$set": data},
                return_document=True  # Return updated document
            )
            
            if result and "_id" in result:
                result["id"] = str(result["_id"])
                del result["_id"]
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=result,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"operation": "update", "collection": self.collection_name}
            )
            
        except Exception as e:
            logger.error(f"MongoDB update failed: {e}", collection=self.collection_name, id=record_id)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "update", "collection": self.collection_name}
            )
    
    async def delete(self, record_id: Union[str, int]) -> QueryResult[bool]:
        """Delete document from MongoDB"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            from bson import ObjectId
            collection = await self._get_collection()
            
            query_id = record_id
            try:
                if isinstance(record_id, str) and len(record_id) == 24:
                    query_id = ObjectId(record_id)
            except:
                pass
            
            result = await collection.delete_one({"_id": query_id})
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=result.deleted_count > 0,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={
                    "operation": "delete",
                    "collection": self.collection_name,
                    "deleted_count": result.deleted_count
                }
            )
            
        except Exception as e:
            logger.error(f"MongoDB delete failed: {e}", collection=self.collection_name, id=record_id)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=False,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "delete", "collection": self.collection_name}
            )
    
    async def find(
        self,
        filters: Dict[str, Any],
        options: QueryOptions = None
    ) -> QueryResult[List[T]]:
        """Find documents in MongoDB"""
        if options is None:
            options = QueryOptions()
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            collection = await self._get_collection()
            
            # Convert filters to MongoDB query format
            mongo_filters = self._convert_filters_to_mongo(filters)
            
            # Build cursor
            cursor = collection.find(mongo_filters)
            
            # Apply sorting
            if options.sort:
                sort_list = [(field, direction) for field, direction in options.sort.items()]
                cursor = cursor.sort(sort_list)
            
            # Apply pagination
            if options.offset:
                cursor = cursor.skip(options.offset)
            if options.limit:
                cursor = cursor.limit(options.limit)
            
            # Execute query
            documents = []
            async for doc in cursor:
                if "_id" in doc:
                    doc["id"] = str(doc["_id"])
                    del doc["_id"]
                documents.append(doc)
            
            # Get count if requested
            count = None
            if options.include_count:
                count = await collection.count_documents(mongo_filters)
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=documents,
                count=count,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={
                    "operation": "find",
                    "collection": self.collection_name,
                    "filters": filters,
                    "options": asdict(options)
                }
            )
            
        except Exception as e:
            logger.error(f"MongoDB find failed: {e}", collection=self.collection_name, filters=filters)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=[],
                count=0,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "find", "collection": self.collection_name}
            )
    
    def _convert_filters_to_mongo(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Convert generic filters to MongoDB query format"""
        mongo_filters = {}
        
        for key, value in filters.items():
            if isinstance(value, dict):
                # Handle operators
                mongo_value = {}
                for op, op_value in value.items():
                    if op == "$gt":
                        mongo_value["$gt"] = op_value
                    elif op == "$lt":
                        mongo_value["$lt"] = op_value
                    elif op == "$in":
                        mongo_value["$in"] = op_value
                    elif op == "$like":
                        mongo_value["$regex"] = f".*{op_value}.*"
                        mongo_value["$options"] = "i"  # Case insensitive
                mongo_filters[key] = mongo_value
            else:
                mongo_filters[key] = value
        
        return mongo_filters


class InfluxDBRepository(BaseRepository[T]):
    """InfluxDB repository for time-series data"""
    
    def __init__(self, measurement: str, bucket: str = "lyo_metrics"):
        super().__init__(StorageEngine.INFLUXDB)
        self.measurement = measurement
        self.bucket = bucket
        self._client = None
    
    async def _get_client(self):
        """Get InfluxDB client"""
        if not self._client:
            url = getattr(settings, 'INFLUXDB_URL', 'http://localhost:8086')
            token = getattr(settings, 'INFLUXDB_TOKEN', 'your-token')
            org = getattr(settings, 'INFLUXDB_ORG', 'lyo-org')
            
            self._client = InfluxDBClientAsync(url=url, token=token, org=org)
        
        return self._client
    
    async def create(self, data: Dict[str, Any]) -> QueryResult[T]:
        """Write point to InfluxDB"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            client = await self._get_client()
            write_api = client.write_api()
            
            # Create point
            point = Point(self.measurement)
            
            # Add timestamp if not provided
            if 'time' not in data:
                point = point.time(datetime.utcnow())
            else:
                point = point.time(data['time'])
                del data['time']
            
            # Separate tags and fields
            tags = data.get('tags', {})
            fields = data.get('fields', {})
            
            # If no explicit tags/fields, treat string values as tags, numeric as fields
            if not tags and not fields:
                for key, value in data.items():
                    if key in ['tags', 'fields']:
                        continue
                    
                    if isinstance(value, (str, bool)):
                        point = point.tag(key, str(value))
                    elif isinstance(value, (int, float)):
                        point = point.field(key, value)
                    else:
                        point = point.field(key, str(value))
            else:
                # Add explicit tags and fields
                for key, value in tags.items():
                    point = point.tag(key, str(value))
                
                for key, value in fields.items():
                    point = point.field(key, value)
            
            # Write point
            await write_api.write(bucket=self.bucket, record=point)
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data={"success": True, "measurement": self.measurement},
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"operation": "create", "measurement": self.measurement}
            )
            
        except Exception as e:
            logger.error(f"InfluxDB create failed: {e}", measurement=self.measurement)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=None,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "create", "measurement": self.measurement}
            )
    
    async def get_by_id(self, record_id: Union[str, int]) -> QueryResult[T]:
        """InfluxDB doesn't have traditional ID-based lookups"""
        return QueryResult(
            data=None,
            storage_engine=self.storage_engine,
            metadata={"error": "get_by_id not supported for time-series data"}
        )
    
    async def update(self, record_id: Union[str, int], data: Dict[str, Any]) -> QueryResult[T]:
        """InfluxDB doesn't support updates - append only"""
        return QueryResult(
            data=None,
            storage_engine=self.storage_engine,
            metadata={"error": "update not supported for time-series data"}
        )
    
    async def delete(self, record_id: Union[str, int]) -> QueryResult[bool]:
        """InfluxDB supports deletion by time range and tags"""
        # Implementation would depend on specific requirements
        return QueryResult(
            data=False,
            storage_engine=self.storage_engine,
            metadata={"error": "delete by ID not supported for time-series data"}
        )
    
    async def find(
        self,
        filters: Dict[str, Any],
        options: QueryOptions = None
    ) -> QueryResult[List[T]]:
        """Query time-series data from InfluxDB"""
        if options is None:
            options = QueryOptions()
        
        start_time = asyncio.get_event_loop().time()
        
        try:
            client = await self._get_client()
            query_api = client.query_api()
            
            # Build Flux query
            time_range = filters.get('time_range', '1h')  # Default 1 hour
            query = f'''
                from(bucket: "{self.bucket}")
                |> range(start: -{time_range})
                |> filter(fn: (r) => r["_measurement"] == "{self.measurement}")
            '''
            
            # Add additional filters
            for key, value in filters.items():
                if key != 'time_range':
                    if isinstance(value, str):
                        query += f'|> filter(fn: (r) => r["{key}"] == "{value}")\n'
                    else:
                        query += f'|> filter(fn: (r) => r["{key}"] == {value})\n'
            
            # Add limit
            if options.limit:
                query += f'|> limit(n: {options.limit})\n'
            
            # Execute query
            tables = await query_api.query(query)
            
            # Process results
            records = []
            for table in tables:
                for record in table.records:
                    records.append({
                        "time": record.get_time(),
                        "measurement": record.get_measurement(),
                        "field": record.get_field(),
                        "value": record.get_value(),
                        **{k: v for k, v in record.values.items() if k.startswith("_") or k in filters}
                    })
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=records,
                count=len(records),
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={
                    "operation": "find",
                    "measurement": self.measurement,
                    "filters": filters
                }
            )
            
        except Exception as e:
            logger.error(f"InfluxDB find failed: {e}", measurement=self.measurement, filters=filters)
            execution_time = asyncio.get_event_loop().time() - start_time
            
            return QueryResult(
                data=[],
                count=0,
                execution_time=execution_time,
                storage_engine=self.storage_engine,
                metadata={"error": str(e), "operation": "find", "measurement": self.measurement}
            )


class UnifiedDataManager:
    """Unified interface for all storage engines"""
    
    def __init__(self):
        self._repositories: Dict[str, BaseRepository] = {}
        self._storage_routing: Dict[DataCategory, StorageEngine] = {
            DataCategory.TRANSACTIONAL: StorageEngine.POSTGRESQL,
            DataCategory.DOCUMENT: StorageEngine.MONGODB,
            DataCategory.CACHE: StorageEngine.REDIS,
            DataCategory.TIME_SERIES: StorageEngine.INFLUXDB,
        }
    
    def get_repository(
        self,
        entity_name: str,
        category: DataCategory,
        **kwargs
    ) -> BaseRepository:
        """Get appropriate repository for entity"""
        
        cache_key = f"{entity_name}:{category.value}"
        
        if cache_key not in self._repositories:
            storage_engine = self._storage_routing[category]
            
            if storage_engine == StorageEngine.POSTGRESQL:
                self._repositories[cache_key] = PostgreSQLRepository(
                    table_name=kwargs.get('table_name', entity_name),
                    model_class=kwargs.get('model_class')
                )
            elif storage_engine == StorageEngine.MONGODB:
                self._repositories[cache_key] = MongoDBRepository(
                    collection_name=kwargs.get('collection_name', entity_name),
                    database_name=kwargs.get('database_name', 'lyo_app')
                )
            elif storage_engine == StorageEngine.INFLUXDB:
                self._repositories[cache_key] = InfluxDBRepository(
                    measurement=kwargs.get('measurement', entity_name),
                    bucket=kwargs.get('bucket', 'lyo_metrics')
                )
            else:
                raise ValueError(f"Repository for {storage_engine} not implemented")
        
        return self._repositories[cache_key]
    
    async def create_with_caching(
        self,
        entity_name: str,
        category: DataCategory,
        data: Dict[str, Any],
        cache_ttl: int = 300,
        **repo_kwargs
    ) -> QueryResult:
        """Create with automatic caching"""
        
        # Create in primary storage
        repo = self.get_repository(entity_name, category, **repo_kwargs)
        result = await repo.create(data)
        
        # Cache if successful and caching is enabled
        if result.data and category != DataCategory.CACHE:
            try:
                cache_manager = get_cache_manager()
                cache_key = f"{entity_name}:{result.data.get('id', 'unknown')}"
                await cache_manager.set(cache_key, result.data, ttl=cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to cache created entity: {e}")
        
        return result
    
    async def get_with_caching(
        self,
        entity_name: str,
        category: DataCategory,
        record_id: Union[str, int],
        cache_ttl: int = 300,
        **repo_kwargs
    ) -> QueryResult:
        """Get with cache-aside pattern"""
        
        cache_key = f"{entity_name}:{record_id}"
        
        # Try cache first (except for time-series data)
        if category != DataCategory.TIME_SERIES:
            try:
                cache_manager = get_cache_manager()
                cached_data = await cache_manager.get(cache_key)
                
                if cached_data:
                    return QueryResult(
                        data=cached_data,
                        storage_engine=StorageEngine.REDIS,
                        metadata={"cache_hit": True, "original_category": category.value}
                    )
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")
        
        # Get from primary storage
        repo = self.get_repository(entity_name, category, **repo_kwargs)
        result = await repo.get_by_id(record_id)
        
        # Cache result if successful
        if result.data and category != DataCategory.CACHE:
            try:
                cache_manager = get_cache_manager()
                await cache_manager.set(cache_key, result.data, ttl=cache_ttl)
            except Exception as e:
                logger.warning(f"Failed to cache retrieved entity: {e}")
        
        return result
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of all storage engines"""
        health_status = {}
        
        # PostgreSQL
        try:
            pg_repo = PostgreSQLRepository("health_check")
            async with pg_repo.get_session() as session:
                await session.execute(text("SELECT 1"))
            health_status["postgresql"] = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            health_status["postgresql"] = {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
        
        # MongoDB
        try:
            mongo_repo = MongoDBRepository("health_check")
            collection = await mongo_repo._get_collection()
            await collection.find_one({})  # Simple query
            health_status["mongodb"] = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            health_status["mongodb"] = {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
        
        # Redis
        try:
            cache_manager = get_cache_manager()
            await cache_manager.redis_client.ping()
            health_status["redis"] = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            health_status["redis"] = {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
        
        # InfluxDB
        try:
            influx_repo = InfluxDBRepository("health_check")
            client = await influx_repo._get_client()
            health_api = client.health_api()
            health = await health_api.health()
            health_status["influxdb"] = {"status": "healthy" if health.status == "pass" else "degraded", "timestamp": datetime.utcnow().isoformat()}
        except Exception as e:
            health_status["influxdb"] = {"status": "unhealthy", "error": str(e), "timestamp": datetime.utcnow().isoformat()}
        
        overall_healthy = all(status["status"] == "healthy" for status in health_status.values())
        
        return {
            "overall_status": "healthy" if overall_healthy else "degraded",
            "engines": health_status,
            "timestamp": datetime.utcnow().isoformat()
        }


# Global data manager instance
_data_manager: Optional[UnifiedDataManager] = None


def get_data_manager() -> UnifiedDataManager:
    """Get global unified data manager instance"""
    global _data_manager
    if _data_manager is None:
        _data_manager = UnifiedDataManager()
    return _data_manager
