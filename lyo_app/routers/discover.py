"""
Discover Router - Educational places, trending topics, and curated content.
Serves reference data for the Discover tab (places, trending resources).
"""

import math
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.auth.models import User

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discover", tags=["Discover"])


# ============================================================================
# Pydantic Models
# ============================================================================

class Place(BaseModel):
    id: str
    name: str
    description: str
    category: str
    lat: float
    lng: float
    rating: float
    review_count: int
    image_url: str
    address: str
    website: str = ""
    tags: list[str] = []
    is_featured: bool = False


class PlaceDetail(Place):
    hours: str = ""
    phone: str = ""
    reviews: list[dict] = []


class PlacesResponse(BaseModel):
    places: list[Place]
    total: int


class TrendingTopic(BaseModel):
    name: str
    count: int
    icon: str


class TrendingResource(BaseModel):
    title: str
    type: str
    url: str


class TrendingResponse(BaseModel):
    topics: list[TrendingTopic]
    resources: list[TrendingResource]


# ============================================================================
# Seed Data — 15 Real Famous Educational Places
# ============================================================================

SEED_PLACES: list[PlaceDetail] = [
    PlaceDetail(
        id="place-001",
        name="Smithsonian Institution",
        description="The world's largest museum, education, and research complex with 21 museums and galleries along the National Mall.",
        category="museum",
        lat=38.8881,
        lng=-77.0120,
        rating=4.8,
        review_count=12540,
        image_url="https://images.unsplash.com/photo-1578662996442-48f60103fc96?w=800",
        address="1000 Jefferson Dr SW, Washington, DC 20560, USA",
        website="https://www.si.edu",
        tags=["history", "science", "art", "free-admission"],
        is_featured=True,
        hours="10:00 AM - 5:30 PM daily",
        phone="+1-202-633-1000",
        reviews=[
            {"user": "Emily R.", "rating": 5, "text": "Absolutely incredible collection. Could spend weeks here."},
            {"user": "Marcus J.", "rating": 5, "text": "The Air and Space Museum alone is worth the trip."},
        ],
    ),
    PlaceDetail(
        id="place-002",
        name="Massachusetts Institute of Technology",
        description="A world-renowned research university pushing the boundaries of science, engineering, and technology innovation.",
        category="university",
        lat=42.3601,
        lng=-71.0942,
        rating=4.9,
        review_count=8720,
        image_url="https://images.unsplash.com/photo-1564981797816-1043664bf78d?w=800",
        address="77 Massachusetts Ave, Cambridge, MA 02139, USA",
        website="https://www.mit.edu",
        tags=["engineering", "technology", "research", "innovation"],
        is_featured=True,
        hours="Campus open 24/7; visitor center 9 AM - 5 PM",
        phone="+1-617-253-1000",
        reviews=[
            {"user": "Sarah L.", "rating": 5, "text": "The campus tour is fascinating. World-class facilities."},
            {"user": "David K.", "rating": 5, "text": "MIT OpenCourseWare changed my life."},
        ],
    ),
    PlaceDetail(
        id="place-003",
        name="British Museum",
        description="A public museum dedicated to human history, art, and culture, housing a permanent collection of over 8 million works.",
        category="museum",
        lat=51.5194,
        lng=-0.1270,
        rating=4.7,
        review_count=15230,
        image_url="https://images.unsplash.com/photo-1590080875515-8a3a8dc5735e?w=800",
        address="Great Russell St, London WC1B 3DG, United Kingdom",
        website="https://www.britishmuseum.org",
        tags=["history", "archaeology", "art", "free-admission"],
        is_featured=True,
        hours="10:00 AM - 5:00 PM (Fri until 8:30 PM)",
        phone="+44-20-7323-8299",
        reviews=[
            {"user": "Oliver P.", "rating": 5, "text": "The Rosetta Stone and Egyptian galleries are extraordinary."},
            {"user": "Aisha M.", "rating": 4, "text": "Vast collection. Plan to come multiple times."},
        ],
    ),
    PlaceDetail(
        id="place-004",
        name="Library of Congress",
        description="The largest library in the world, with millions of books, recordings, photographs, newspapers, maps, and manuscripts.",
        category="library",
        lat=38.8887,
        lng=-77.0047,
        rating=4.8,
        review_count=6840,
        image_url="https://images.unsplash.com/photo-1507842217343-583bb7270b66?w=800",
        address="101 Independence Ave SE, Washington, DC 20540, USA",
        website="https://www.loc.gov",
        tags=["books", "research", "history", "archives"],
        is_featured=True,
        hours="8:30 AM - 4:30 PM Mon-Sat",
        phone="+1-202-707-5000",
        reviews=[
            {"user": "Thomas W.", "rating": 5, "text": "The architecture alone is worth a visit. The reading rooms are stunning."},
            {"user": "Grace H.", "rating": 5, "text": "An unparalleled research resource for any scholar."},
        ],
    ),
    PlaceDetail(
        id="place-005",
        name="CERN",
        description="The European Organization for Nuclear Research, home to the Large Hadron Collider and groundbreaking particle physics research.",
        category="lab",
        lat=46.2330,
        lng=6.0557,
        rating=4.9,
        review_count=4520,
        image_url="https://images.unsplash.com/photo-1635070041078-e363dbe005cb?w=800",
        address="Esplanade des Particules 1, 1211 Meyrin, Geneva, Switzerland",
        website="https://home.cern",
        tags=["physics", "science", "research", "technology"],
        is_featured=True,
        hours="Tours by reservation; exhibitions 9 AM - 5 PM",
        phone="+41-22-767-8484",
        reviews=[
            {"user": "Pierre D.", "rating": 5, "text": "Mind-blowing experience seeing where the Higgs boson was discovered."},
            {"user": "Yuki T.", "rating": 5, "text": "The interactive exhibits make complex physics accessible."},
        ],
    ),
    PlaceDetail(
        id="place-006",
        name="Stanford University",
        description="A leading research university known for its entrepreneurial spirit, academic excellence, and proximity to Silicon Valley.",
        category="university",
        lat=37.4275,
        lng=-122.1697,
        rating=4.8,
        review_count=7630,
        image_url="https://images.unsplash.com/photo-1585060544812-6b45742d762f?w=800",
        address="450 Serra Mall, Stanford, CA 94305, USA",
        website="https://www.stanford.edu",
        tags=["technology", "entrepreneurship", "research", "innovation"],
        is_featured=False,
        hours="Campus open daily; visitor center 10 AM - 4 PM",
        phone="+1-650-723-2300",
        reviews=[
            {"user": "Jennifer C.", "rating": 5, "text": "Beautiful campus with incredible academic resources."},
            {"user": "Raj P.", "rating": 5, "text": "The engineering and CS programs are world-class."},
        ],
    ),
    PlaceDetail(
        id="place-007",
        name="Louvre Museum",
        description="The world's most-visited art museum and a historic monument in Paris, home to the Mona Lisa and Venus de Milo.",
        category="museum",
        lat=48.8606,
        lng=2.3376,
        rating=4.7,
        review_count=21450,
        image_url="https://images.unsplash.com/photo-1499856871958-5b9627545d1a?w=800",
        address="Rue de Rivoli, 75001 Paris, France",
        website="https://www.louvre.fr",
        tags=["art", "history", "culture", "architecture"],
        is_featured=True,
        hours="9:00 AM - 6:00 PM (Wed & Fri until 9:45 PM), Closed Tuesdays",
        phone="+33-1-40-20-53-17",
        reviews=[
            {"user": "Claire B.", "rating": 5, "text": "An art lover's paradise. The building itself is a masterpiece."},
            {"user": "Antonio G.", "rating": 4, "text": "Go early to beat the crowds. Absolutely worth it."},
        ],
    ),
    PlaceDetail(
        id="place-008",
        name="National Museum of Nature and Science",
        description="Japan's premier science museum featuring extensive collections on natural history, science, and technology.",
        category="museum",
        lat=35.7164,
        lng=139.7764,
        rating=4.6,
        review_count=5890,
        image_url="https://images.unsplash.com/photo-1540959733332-eab4deabeeaf?w=800",
        address="7-20 Ueno Park, Taito City, Tokyo 110-8718, Japan",
        website="https://www.kahaku.go.jp",
        tags=["science", "natural-history", "technology", "dinosaurs"],
        is_featured=False,
        hours="9:00 AM - 5:00 PM (Fri & Sat until 8:00 PM), Closed Mondays",
        phone="+81-3-5777-8600",
        reviews=[
            {"user": "Kenji S.", "rating": 5, "text": "Incredible dinosaur exhibits and hands-on science areas."},
            {"user": "Lisa M.", "rating": 4, "text": "Great for families. The planetarium is spectacular."},
        ],
    ),
    PlaceDetail(
        id="place-009",
        name="Harvard University",
        description="The oldest institution of higher education in the US, renowned for academic excellence across all disciplines.",
        category="university",
        lat=42.3770,
        lng=-71.1167,
        rating=4.8,
        review_count=9130,
        image_url="https://images.unsplash.com/photo-1559135197-8a45ea74d367?w=800",
        address="Massachusetts Hall, Cambridge, MA 02138, USA",
        website="https://www.harvard.edu",
        tags=["liberal-arts", "research", "law", "medicine"],
        is_featured=False,
        hours="Campus open daily; tours available",
        phone="+1-617-495-1000",
        reviews=[
            {"user": "Michael T.", "rating": 5, "text": "Walking through Harvard Yard is inspiring."},
            {"user": "Priya N.", "rating": 5, "text": "The libraries alone make this a scholarly paradise."},
        ],
    ),
    PlaceDetail(
        id="place-010",
        name="Bodleian Library",
        description="One of the oldest libraries in Europe, serving as the main research library of the University of Oxford since 1602.",
        category="library",
        lat=51.7548,
        lng=-1.2544,
        rating=4.8,
        review_count=3920,
        image_url="https://images.unsplash.com/photo-1481627834876-b7833e8f5570?w=800",
        address="Broad St, Oxford OX1 3BG, United Kingdom",
        website="https://www.bodleian.ox.ac.uk",
        tags=["books", "history", "architecture", "research"],
        is_featured=False,
        hours="9:00 AM - 5:00 PM Mon-Sat",
        phone="+44-1865-277162",
        reviews=[
            {"user": "James F.", "rating": 5, "text": "The Radcliffe Camera is breathtaking. A must-see in Oxford."},
            {"user": "Sophie R.", "rating": 5, "text": "The guided tour reveals centuries of hidden history."},
        ],
    ),
    PlaceDetail(
        id="place-011",
        name="Exploratorium",
        description="A hands-on science museum in San Francisco dedicated to making science accessible through interactive exhibits and experiences.",
        category="museum",
        lat=37.8017,
        lng=-122.3975,
        rating=4.7,
        review_count=6340,
        image_url="https://images.unsplash.com/photo-1526587367011-2898b2a6de42?w=800",
        address="Pier 15, San Francisco, CA 94111, USA",
        website="https://www.exploratorium.edu",
        tags=["science", "interactive", "hands-on", "family-friendly"],
        is_featured=False,
        hours="10:00 AM - 5:00 PM Tue-Sun",
        phone="+1-415-528-4444",
        reviews=[
            {"user": "Chris D.", "rating": 5, "text": "Best interactive science museum I've ever visited."},
            {"user": "Amanda K.", "rating": 4, "text": "Kids and adults both love this place."},
        ],
    ),
    PlaceDetail(
        id="place-012",
        name="Natural History Museum",
        description="A world-leading museum of natural history specimens and research, featuring the famous Diplodocus skeleton and Darwin Centre.",
        category="museum",
        lat=51.4967,
        lng=-0.1764,
        rating=4.7,
        review_count=11870,
        image_url="https://images.unsplash.com/photo-1574071318508-1cdbab80d002?w=800",
        address="Cromwell Rd, South Kensington, London SW7 5BD, United Kingdom",
        website="https://www.nhm.ac.uk",
        tags=["natural-history", "science", "dinosaurs", "free-admission"],
        is_featured=False,
        hours="10:00 AM - 5:50 PM daily",
        phone="+44-20-7942-5000",
        reviews=[
            {"user": "Edward B.", "rating": 5, "text": "The Hintze Hall with the blue whale is spectacular."},
            {"user": "Mei L.", "rating": 5, "text": "Free entry and world-class exhibits. London at its best."},
        ],
    ),
    PlaceDetail(
        id="place-013",
        name="Max Planck Institute",
        description="One of Germany's premier research organizations, advancing fundamental science across physics, biology, and more.",
        category="lab",
        lat=48.2480,
        lng=11.6076,
        rating=4.7,
        review_count=2150,
        image_url="https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=800",
        address="Boltzmannstrasse 2, 85748 Garching, Munich, Germany",
        website="https://www.mpg.de",
        tags=["physics", "biology", "research", "science"],
        is_featured=False,
        hours="By appointment; public lectures periodically",
        phone="+49-89-2108-0",
        reviews=[
            {"user": "Hans M.", "rating": 5, "text": "Cutting-edge research facilities. Public lectures are very informative."},
            {"user": "Anna W.", "rating": 4, "text": "Fascinating insight into German scientific research."},
        ],
    ),
    PlaceDetail(
        id="place-014",
        name="National Library of China",
        description="The largest library in Asia and one of the largest in the world, with over 37 million items in its collections.",
        category="library",
        lat=39.9427,
        lng=116.3186,
        rating=4.5,
        review_count=3480,
        image_url="https://images.unsplash.com/photo-1521587760476-6c12a4b040da?w=800",
        address="33 Zhongguancun S St, Haidian District, Beijing 100081, China",
        website="https://www.nlc.cn",
        tags=["books", "archives", "research", "culture"],
        is_featured=False,
        hours="9:00 AM - 5:00 PM Mon-Fri",
        phone="+86-10-8854-5426",
        reviews=[
            {"user": "Wei Z.", "rating": 5, "text": "An extraordinary collection of Chinese and international literature."},
            {"user": "Lin C.", "rating": 4, "text": "The digital resources are impressive and constantly growing."},
        ],
    ),
    PlaceDetail(
        id="place-015",
        name="Bibliotheca Alexandrina",
        description="A major library and cultural center on the shore of the Mediterranean, a modern tribute to the ancient Library of Alexandria.",
        category="library",
        lat=31.2089,
        lng=29.9092,
        rating=4.6,
        review_count=4190,
        image_url="https://images.unsplash.com/photo-1568667256549-094345857637?w=800",
        address="Al Azaritah WA Ash Shatebi, Alexandria, Egypt",
        website="https://www.bibalex.org",
        tags=["books", "culture", "history", "architecture"],
        is_featured=True,
        hours="10:00 AM - 7:00 PM Sun-Thu",
        phone="+20-3-483-9999",
        reviews=[
            {"user": "Omar A.", "rating": 5, "text": "A stunning modern building with an incredible mission. The architecture is breathtaking."},
            {"user": "Maria S.", "rating": 5, "text": "A must-visit in Alexandria. The exhibitions are world-class."},
        ],
    ),
]

VALID_CATEGORIES = {"museum", "library", "university", "lab", "coworking", "landmark"}


# ============================================================================
# Helper: Haversine distance (km)
# ============================================================================

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/places", response_model=PlacesResponse)
async def list_places(
    lat: Optional[float] = Query(None, description="Latitude for proximity search"),
    lng: Optional[float] = Query(None, description="Longitude for proximity search"),
    radius_km: float = Query(50.0, ge=1, le=20000, description="Search radius in km"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """List educational places, optionally filtered by location and category."""
    results = list(SEED_PLACES)

    # Category filter
    if category:
        cat = category.lower()
        if cat not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category '{category}'. Valid: {', '.join(sorted(VALID_CATEGORIES))}",
            )
        results = [p for p in results if p.category == cat]

    # Proximity filter
    if lat is not None and lng is not None:
        results = [
            p for p in results if _haversine_km(lat, lng, p.lat, p.lng) <= radius_km
        ]
        # Sort by distance
        results.sort(key=lambda p: _haversine_km(lat, lng, p.lat, p.lng))
    else:
        # Default sort: featured first, then by rating
        results.sort(key=lambda p: (-int(p.is_featured), -p.rating))

    total = len(results)

    # Pagination
    start = (page - 1) * per_page
    end = start + per_page
    page_results = results[start:end]

    # Return as Place (not PlaceDetail) to hide hours/phone/reviews in list view
    places_out = [Place(**p.model_dump(exclude={"hours", "phone", "reviews"})) for p in page_results]

    return PlacesResponse(places=places_out, total=total)


@router.get("/places/{place_id}", response_model=PlaceDetail)
async def get_place(
    place_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed information about a single educational place."""
    for place in SEED_PLACES:
        if place.id == place_id:
            return place
    raise HTTPException(status_code=404, detail=f"Place '{place_id}' not found")


@router.get("/trending", response_model=TrendingResponse)
async def get_trending(
    current_user: User = Depends(get_current_user),
):
    """Get trending topics and resources for the discover page."""
    topics = [
        TrendingTopic(name="Artificial Intelligence", count=12840, icon="brain"),
        TrendingTopic(name="Quantum Computing", count=8920, icon="atom"),
        TrendingTopic(name="Climate Science", count=7650, icon="leaf"),
        TrendingTopic(name="Neuroscience", count=6430, icon="activity"),
        TrendingTopic(name="Space Exploration", count=5870, icon="rocket"),
        TrendingTopic(name="Biotechnology", count=4920, icon="dna"),
        TrendingTopic(name="Machine Learning", count=11200, icon="cpu"),
        TrendingTopic(name="Renewable Energy", count=3810, icon="zap"),
    ]

    resources = [
        TrendingResource(
            title="MIT OpenCourseWare: Introduction to Deep Learning",
            type="course",
            url="https://ocw.mit.edu/courses/6-s191-introduction-to-deep-learning",
        ),
        TrendingResource(
            title="Khan Academy: AP Physics 1",
            type="course",
            url="https://www.khanacademy.org/science/ap-physics-1",
        ),
        TrendingResource(
            title="Nature: Recent Advances in CRISPR",
            type="article",
            url="https://www.nature.com/subjects/crispr-cas9",
        ),
        TrendingResource(
            title="Stanford CS229: Machine Learning",
            type="lecture",
            url="https://cs229.stanford.edu",
        ),
        TrendingResource(
            title="3Blue1Brown: Essence of Linear Algebra",
            type="video",
            url="https://www.3blue1brown.com/topics/linear-algebra",
        ),
        TrendingResource(
            title="Coursera: The Science of Well-Being",
            type="course",
            url="https://www.coursera.org/learn/the-science-of-well-being",
        ),
    ]

    return TrendingResponse(topics=topics, resources=resources)
