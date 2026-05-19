"""
Unit tests for DBSCAN-based clustering algorithm.

Covers: group_rides() from app/services/clustering_algorithm.py
- Geo-spatial grouping correctness
- Strict vs non-strict mode
- Edge cases: empty input, single ride, huge radius, group_size=1
- All tests are pure Python — no DB, no HTTP.
"""
import pytest

from app.services.clustering_algorithm import group_rides

pytestmark = pytest.mark.unit


# ─── Reusable location fixtures ───────────────────────────────────────────────
def _ride(user: str, lat: float, lon: float) -> dict:
    return {"user": user, "lat": lat, "lon": lon, "departure": "2026-01-01 09:00:00"}


# Bangalore city clusters (well-separated, >10 km apart each)
DOWNTOWN = [
    _ride("d1", 12.9716, 77.5946),
    _ride("d2", 12.9720, 77.5940),
    _ride("d3", 12.9718, 77.5942),
]
AIRPORT = [
    _ride("a1", 13.1986, 77.7066),
    _ride("a2", 13.1988, 77.7062),
]
ISOLATED = [_ride("iso", 11.0000, 76.0000)]  # ~250 km away


# ─────────────────────────────────────────────────────────────────────────────
# Basic correctness
# ─────────────────────────────────────────────────────────────────────────────
class TestGroupRidesBasic:
    def test_empty_input_returns_empty_list(self):
        assert group_rides([], radius_km=1.0, group_size=4, strict_grouping=False) == []

    def test_single_ride_non_strict_forms_group_of_one(self):
        rides = [_ride("solo", 12.97, 77.59)]
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=False)
        assert len(groups) == 1
        assert groups[0][0]["user"] == "solo"

    def test_single_ride_strict_mode_yields_no_groups(self):
        """Strict mode: a group of 1 cannot satisfy group_size=4."""
        rides = [_ride("solo", 12.97, 77.59)]
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=True)
        assert groups == []

    def test_all_rides_accounted_for_in_non_strict_mode(self):
        rides = DOWNTOWN + AIRPORT + ISOLATED
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=False)
        assigned = sum(len(g) for g in groups)
        assert assigned == len(rides)

    def test_no_group_exceeds_group_size(self):
        rides = DOWNTOWN * 5  # 15 rides at same cluster
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=False)
        for group in groups:
            assert len(group) <= 4

    def test_return_type_is_list_of_lists_of_dicts(self):
        groups = group_rides(DOWNTOWN, radius_km=1.0, group_size=4, strict_grouping=False)
        assert isinstance(groups, list)
        for g in groups:
            assert isinstance(g, list)
            for ride in g:
                assert isinstance(ride, dict)
                assert {"user", "lat", "lon"}.issubset(ride.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Clustering accuracy
# ─────────────────────────────────────────────────────────────────────────────
class TestClusteringAccuracy:
    def test_spatially_close_rides_grouped_together(self):
        """All 3 downtown rides (<0.1 km apart) must end up in one group."""
        groups = group_rides(DOWNTOWN, radius_km=1.0, group_size=4, strict_grouping=False)
        assert any(len(g) == 3 for g in groups)

    def test_distant_clusters_are_separated(self):
        """Downtown (12.97°) vs Airport (13.19°) — ~30 km — must be separate clusters."""
        rides = DOWNTOWN + AIRPORT
        groups = group_rides(rides, radius_km=1.0, group_size=10, strict_grouping=False)
        assert len(groups) == 2
        sizes = sorted(len(g) for g in groups)
        assert sizes == [2, 3]

    def test_isolated_ride_forms_its_own_group(self):
        rides = DOWNTOWN + ISOLATED
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=False)
        isolated_groups = [g for g in groups if any(r["user"] == "iso" for r in g)]
        assert len(isolated_groups) == 1
        assert len(isolated_groups[0]) == 1

    def test_rides_not_duplicated_across_groups(self):
        """Each ride must appear in exactly one group."""
        rides = DOWNTOWN + AIRPORT + ISOLATED
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=False)
        all_users = [r["user"] for g in groups for r in g]
        assert len(all_users) == len(set(all_users)), "Duplicate ride assignment detected"


# ─────────────────────────────────────────────────────────────────────────────
# Strict mode
# ─────────────────────────────────────────────────────────────────────────────
class TestStrictGroupingMode:
    def test_exact_full_group_emitted(self):
        rides = [_ride(f"u{i}", 12.9716 + i * 0.0001, 77.5946) for i in range(4)]
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=True)
        assert len(groups) == 1
        assert len(groups[0]) == 4

    def test_partial_cluster_not_emitted_in_strict_mode(self):
        rides = [_ride(f"u{i}", 12.9716 + i * 0.0001, 77.5946) for i in range(3)]
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=True)
        assert groups == []

    def test_mixed_full_and_partial_clusters_strict(self):
        """4 close rides → 1 group emitted; 2 far rides → discarded (incomplete)."""
        full_cluster = [_ride(f"c{i}", 12.9716 + i * 0.0001, 77.5946) for i in range(4)]
        partial_cluster = [_ride(f"f{i}", 13.20 + i * 0.0001, 77.71) for i in range(2)]
        groups = group_rides(
            full_cluster + partial_cluster,
            radius_km=1.0,
            group_size=4,
            strict_grouping=True,
        )
        assert len(groups) == 1
        assert len(groups[0]) == 4

    def test_two_full_clusters_both_emitted_in_strict(self):
        """Two geographically separate full-capacity clusters both emitted."""
        cluster_a = [_ride(f"a{i}", 12.97 + i * 0.0001, 77.59) for i in range(4)]
        cluster_b = [_ride(f"b{i}", 13.20 + i * 0.0001, 77.71) for i in range(4)]
        groups = group_rides(
            cluster_a + cluster_b, radius_km=1.0, group_size=4, strict_grouping=True
        )
        assert len(groups) == 2
        assert all(len(g) == 4 for g in groups)


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases & boundary conditions
# ─────────────────────────────────────────────────────────────────────────────
class TestEdgeCases:
    def test_very_small_radius_isolates_each_ride(self):
        """Rides 1° apart (>100 km) must each be their own cluster at 0.001 km radius."""
        rides = [_ride(f"u{i}", 12.97 + i, 77.59) for i in range(5)]
        groups = group_rides(rides, radius_km=0.001, group_size=4, strict_grouping=False)
        assert len(groups) == 5

    def test_huge_radius_merges_all_rides(self):
        """500 km radius must swallow all clusters into one."""
        rides = DOWNTOWN + AIRPORT + ISOLATED
        groups = group_rides(rides, radius_km=500.0, group_size=50, strict_grouping=False)
        assert len(groups) == 1
        assert len(groups[0]) == len(rides)

    def test_group_size_one_each_ride_is_own_group(self):
        groups = group_rides(DOWNTOWN, radius_km=1.0, group_size=1, strict_grouping=False)
        assert len(groups) == len(DOWNTOWN)
        assert all(len(g) == 1 for g in groups)

    def test_large_input_no_crash(self):
        """Smoke: 200 rides distributed across 10 clusters must not raise."""
        import math

        rides = []
        for cluster_idx in range(10):
            for ride_idx in range(20):
                lat = 12.97 + cluster_idx * 0.5
                lon = 77.59 + cluster_idx * 0.5
                rides.append(_ride(f"c{cluster_idx}r{ride_idx}", lat, lon))
        groups = group_rides(rides, radius_km=1.0, group_size=4, strict_grouping=False)
        assigned = sum(len(g) for g in groups)
        assert assigned == len(rides)

    def test_result_is_deterministic_for_same_input(self):
        """Same input must always produce groups of the same sizes."""
        rides = DOWNTOWN + AIRPORT
        sizes_run1 = sorted(len(g) for g in group_rides(rides, 1.0, 4, False))
        sizes_run2 = sorted(len(g) for g in group_rides(rides, 1.0, 4, False))
        assert sizes_run1 == sizes_run2
