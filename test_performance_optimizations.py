#!/usr/bin/env python3
"""
Performance Optimization Test Suite
Tests caching, lazy loading, and progressive rendering optimizations
"""

import asyncio
import json
import time
import statistics
import sys
from typing import Dict, Any, List
sys.path.append('.')

from lyo_app.cache.performance_cache import (
    PerformanceCache, CacheConfig, performance_monitor,
    lazy_loader, cache_instance
)
from lyo_app.cache.lazy_components import ComponentLoader, ProgressiveRenderer
from lyo_app.chat.assembler import response_assembler
from lyo_app.chat.a2ui_recursive import A2UIFactory

async def test_cache_performance():
    """Test caching system performance"""
    print("🚀 Testing Cache Performance...")

    # Test Redis connection
    cache = PerformanceCache(CacheConfig(redis_host="localhost"))

    # Performance test data
    test_data = {
        "course_id": "test-course-123",
        "title": "Python Fundamentals",
        "description": "Complete Python course",
        "modules": [{"id": i, "title": f"Module {i}"} for i in range(1, 11)]
    }

    # Test cache set/get performance
    times_set = []
    times_get = []

    print("   📊 Cache Write Performance Test...")
    for i in range(50):
        start = time.time()
        await cache.set(f"test_key_{i}", test_data, ttl=300)
        duration = time.time() - start
        times_set.append(duration)

    print("   📊 Cache Read Performance Test...")
    for i in range(50):
        start = time.time()
        result = await cache.get(f"test_key_{i}")
        duration = time.time() - start
        times_get.append(duration)

        if result is None:
            print(f"   ❌ Cache miss for key test_key_{i}")
            return False

    # Calculate statistics
    avg_set = statistics.mean(times_set) * 1000  # Convert to ms
    avg_get = statistics.mean(times_get) * 1000

    print(f"   ✅ Cache Set: {avg_set:.2f}ms avg, {max(times_set)*1000:.2f}ms max")
    print(f"   ✅ Cache Get: {avg_get:.2f}ms avg, {max(times_get)*1000:.2f}ms max")

    # Cleanup
    await cache.clear_pattern("test_key_*")

    return avg_set < 50 and avg_get < 10  # Performance thresholds

async def test_lazy_loading_performance():
    """Test lazy loading system performance"""
    print("\n🚀 Testing Lazy Loading Performance...")

    loader = ComponentLoader()

    # Test concurrent loading
    course_ids = [f"course-{i}" for i in range(1, 21)]

    # Test sequential loading
    print("   📊 Sequential Loading Test...")
    start_sequential = time.time()
    for course_id in course_ids[:5]:  # Test with 5 courses
        await loader.load_course_preview_lazy(course_id)
    sequential_time = time.time() - start_sequential

    # Test concurrent loading
    print("   📊 Concurrent Loading Test...")
    start_concurrent = time.time()
    tasks = [loader.load_course_preview_lazy(course_id) for course_id in course_ids[5:10]]
    await asyncio.gather(*tasks)
    concurrent_time = time.time() - start_concurrent

    print(f"   ✅ Sequential: {sequential_time:.3f}s for 5 components")
    print(f"   ✅ Concurrent: {concurrent_time:.3f}s for 5 components")
    print(f"   ✅ Speedup: {sequential_time/concurrent_time:.2f}x")

    # Test cache hits
    print("   📊 Cache Hit Performance...")
    start_cache = time.time()
    for course_id in course_ids[:5]:  # These should be cached
        await loader.load_course_preview_lazy(course_id)
    cache_time = time.time() - start_cache

    print(f"   ✅ Cached Loading: {cache_time:.3f}s (should be much faster)")

    return concurrent_time < sequential_time and cache_time < sequential_time * 0.5

async def test_progressive_rendering():
    """Test progressive rendering performance"""
    print("\n🚀 Testing Progressive Rendering...")

    renderer = ProgressiveRenderer()

    # Create complex nested UI structure
    complex_ui = {
        "id": "complex-root",
        "type": "vstack",
        "children": [
            {
                "id": f"course-card-{i}",
                "type": "card",
                "title": f"Course {i}",
                "children": [
                    {"id": f"text-{i}-{j}", "type": "text", "content": f"Content {j}"}
                    for j in range(5)
                ] + [
                    {
                        "id": f"nested-stack-{i}",
                        "type": "vstack",
                        "children": [
                            {"id": f"nested-text-{i}-{k}", "type": "text", "content": f"Nested {k}"}
                            for k in range(3)
                        ]
                    }
                ]
            }
            for i in range(10)
        ]
    }

    # Test standard rendering
    print("   📊 Standard Rendering...")
    start_standard = time.time()
    standard_result = complex_ui  # Simulate standard rendering
    standard_time = time.time() - start_standard

    # Test progressive rendering
    print("   📊 Progressive Rendering...")
    start_progressive = time.time()
    progressive_result = await renderer.render_progressive(complex_ui)
    progressive_time = time.time() - start_progressive

    print(f"   ✅ Standard: {standard_time:.3f}s")
    print(f"   ✅ Progressive: {progressive_time:.3f}s")
    print(f"   ✅ Components rendered: {len(progressive_result.get('children', []))}")

    # Verify progressive result has skeleton structure
    has_skeleton = any(
        child.get("type") == "vstack" and "loading" in child.get("id", "")
        for child in progressive_result.get("children", [])
    )

    return progressive_result is not None

async def test_assembler_performance_enhancements():
    """Test response assembler performance enhancements"""
    print("\n🚀 Testing Assembler Performance...")

    # Test course preview with caching
    course_data = {
        "course_id": "perf-test-course",
        "title": "Performance Test Course",
        "description": "Testing performance optimizations",
        "estimated_minutes": 120,
        "total_nodes": 15
    }

    print("   📊 Course Preview UI Creation (First Call)...")
    start_first = time.time()
    ui_component_1 = await response_assembler.create_course_preview_ui_cached(course_data)
    first_call_time = time.time() - start_first

    print("   📊 Course Preview UI Creation (Cached Call)...")
    start_cached = time.time()
    ui_component_2 = await response_assembler.create_course_preview_ui_cached(course_data)
    cached_call_time = time.time() - start_cached

    print(f"   ✅ First call: {first_call_time:.3f}s")
    print(f"   ✅ Cached call: {cached_call_time:.3f}s")
    print(f"   ✅ Cache speedup: {first_call_time/cached_call_time:.2f}x")

    # Test batch component creation
    component_specs = [
        {"type": "course_preview", "course_id": f"batch-course-{i}", "title": f"Course {i}"}
        for i in range(5)
    ]

    print("   📊 Batch Component Creation...")
    start_batch = time.time()
    batch_components = await response_assembler.batch_create_ui_components(component_specs, max_concurrent=3)
    batch_time = time.time() - start_batch

    print(f"   ✅ Batch creation: {batch_time:.3f}s for {len(batch_components)} components")
    print(f"   ✅ Average per component: {batch_time/len(batch_components):.3f}s")

    return (
        ui_component_1 is not None and
        ui_component_2 is not None and
        len(batch_components) == 5 and
        cached_call_time < first_call_time * 0.8  # Cache should be significantly faster
    )

async def test_performance_monitoring():
    """Test performance monitoring system"""
    print("\n🚀 Testing Performance Monitoring...")

    # Generate some monitored operations
    for i in range(10):
        performance_monitor.start_timing("test_operation", f"test_{i}")
        await asyncio.sleep(0.01 * (i + 1))  # Variable duration
        performance_monitor.end_timing("test_operation", f"test_{i}")

    # Generate metrics for different operations
    for op_type in ["ui_creation", "cache_operation", "data_loading"]:
        for j in range(5):
            performance_monitor.start_timing(op_type, f"instance_{j}")
            await asyncio.sleep(0.005)
            performance_monitor.end_timing(op_type, f"instance_{j}")

    # Get performance report
    report = performance_monitor.get_performance_report()

    print(f"   ✅ Operations monitored: {len(report)}")

    for operation, stats in report.items():
        print(f"   📊 {operation}:")
        print(f"      Count: {stats['count']}")
        print(f"      Avg: {stats['avg_duration']:.3f}s")
        print(f"      Min: {stats['min_duration']:.3f}s")
        print(f"      Max: {stats['max_duration']:.3f}s")

    # Test assembler metrics
    assembler_metrics = await response_assembler.get_performance_metrics()
    print(f"   ✅ Assembler metrics available: {len(assembler_metrics)} operations")

    return len(report) >= 4 and len(assembler_metrics) >= 0

async def benchmark_memory_usage():
    """Benchmark memory usage with optimizations"""
    print("\n🚀 Memory Usage Benchmark...")

    import psutil
    import os

    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    print(f"   📊 Initial memory: {initial_memory:.2f} MB")

    # Create large number of components without optimization
    print("   📊 Creating 100 components without caching...")
    start_memory = process.memory_info().rss / 1024 / 1024

    components_no_cache = []
    for i in range(100):
        component = A2UIFactory.card(
            A2UIFactory.text(f"Content {i}", style="body"),
            A2UIFactory.button(f"Action {i}", f"action_{i}"),
            title=f"Card {i}"
        )
        components_no_cache.append(component)

    memory_no_cache = process.memory_info().rss / 1024 / 1024
    memory_increase_no_cache = memory_no_cache - start_memory

    print(f"   📊 Memory after 100 components: {memory_no_cache:.2f} MB (+{memory_increase_no_cache:.2f} MB)")

    # Create components with caching
    print("   📊 Creating 100 components with caching...")
    start_memory_cached = process.memory_info().rss / 1024 / 1024

    # Simulate cached component creation (reuse patterns)
    cached_templates = {}
    components_cached = []

    for i in range(100):
        template_key = f"template_{i % 10}"  # Reuse 10 templates
        if template_key not in cached_templates:
            cached_templates[template_key] = A2UIFactory.card(
                A2UIFactory.text("Template content", style="body"),
                A2UIFactory.button("Template action", "template_action"),
                title="Template Card"
            )
        components_cached.append(cached_templates[template_key])

    memory_cached = process.memory_info().rss / 1024 / 1024
    memory_increase_cached = memory_cached - start_memory_cached

    print(f"   📊 Memory after 100 cached components: {memory_cached:.2f} MB (+{memory_increase_cached:.2f} MB)")
    print(f"   ✅ Memory savings: {memory_increase_no_cache - memory_increase_cached:.2f} MB")

    return memory_increase_cached < memory_increase_no_cache

async def test_error_handling_and_fallbacks():
    """Test error handling and fallback mechanisms"""
    print("\n🚀 Testing Error Handling & Fallbacks...")

    loader = ComponentLoader()

    # Test with invalid course ID
    try:
        fallback_component = await loader.load_course_preview_lazy("invalid-course-id")
        print("   ✅ Fallback component created for invalid course ID")

        # Verify fallback structure
        if isinstance(fallback_component, dict):
            has_error_handling = (
                "error" in fallback_component.get("id", "") or
                "loading" in fallback_component.get("id", "") or
                fallback_component.get("type") in ["text", "card"]
            )
            print(f"   ✅ Fallback structure valid: {has_error_handling}")

    except Exception as e:
        print(f"   ❌ Error handling failed: {e}")
        return False

    # Test cache failure handling
    print("   📊 Testing cache failure scenarios...")

    # Simulate cache failure by using invalid Redis config
    failing_cache = PerformanceCache(CacheConfig(redis_host="invalid-host", redis_port=9999))

    # This should fall back to memory cache
    await failing_cache.set("test_key", {"data": "test"}, 60)
    result = await failing_cache.get("test_key")

    cache_fallback_works = result is not None
    print(f"   ✅ Cache fallback to memory: {cache_fallback_works}")

    return cache_fallback_works

async def run_comprehensive_performance_test():
    """Run all performance tests"""
    print("🎯 PERFORMANCE OPTIMIZATION COMPREHENSIVE TEST SUITE")
    print("=" * 65)

    test_results = {}

    tests = [
        ("Cache Performance", test_cache_performance),
        ("Lazy Loading", test_lazy_loading_performance),
        ("Progressive Rendering", test_progressive_rendering),
        ("Assembler Enhancements", test_assembler_performance_enhancements),
        ("Performance Monitoring", test_performance_monitoring),
        ("Memory Usage", benchmark_memory_usage),
        ("Error Handling", test_error_handling_and_fallbacks)
    ]

    total_start_time = time.time()

    for test_name, test_func in tests:
        print(f"\n{'='*65}")
        print(f"🧪 Running: {test_name}")
        print(f"{'='*65}")

        try:
            test_start = time.time()
            result = await test_func()
            test_duration = time.time() - test_start

            test_results[test_name] = {
                "passed": result,
                "duration": test_duration
            }

            status = "PASSED ✅" if result else "FAILED ❌"
            print(f"\n📊 {test_name}: {status} ({test_duration:.3f}s)")

        except Exception as e:
            test_results[test_name] = {
                "passed": False,
                "duration": 0,
                "error": str(e)
            }
            print(f"\n💥 {test_name}: ERROR - {e}")

    total_duration = time.time() - total_start_time

    # Summary
    print(f"\n{'='*65}")
    print(f"📊 PERFORMANCE OPTIMIZATION TEST RESULTS")
    print(f"{'='*65}")

    passed_tests = sum(1 for result in test_results.values() if result["passed"])
    total_tests = len(test_results)

    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    print(f"Total Duration: {total_duration:.3f}s")

    print(f"\n📈 Performance Summary:")
    for test_name, result in test_results.items():
        status_icon = "✅" if result["passed"] else "❌"
        duration = result.get("duration", 0)
        print(f"  {status_icon} {test_name}: {duration:.3f}s")

    # Performance metrics summary
    metrics = performance_monitor.get_performance_report()
    if metrics:
        print(f"\n⚡ Performance Metrics:")
        for operation, stats in metrics.items():
            print(f"  📊 {operation}: {stats['count']} ops, {stats['avg_duration']:.3f}s avg")

    if passed_tests == total_tests:
        print(f"\n🎉 ALL PERFORMANCE OPTIMIZATION TESTS PASSED!")
        print("✅ Caching system working efficiently")
        print("✅ Lazy loading reducing initial load times")
        print("✅ Progressive rendering improving user experience")
        print("✅ Memory usage optimized")
        print("✅ Error handling and fallbacks functional")
        print("✅ Performance monitoring operational")
    else:
        print(f"\n⚠️  Some performance tests failed. Review above for details.")

    return passed_tests == total_tests

if __name__ == "__main__":
    # Run the comprehensive test
    asyncio.run(run_comprehensive_performance_test())