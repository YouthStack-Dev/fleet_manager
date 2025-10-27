import numpy as np
from sklearn.cluster import DBSCAN

def group_rides(rides, radius_km, group_size, strict_grouping):
    """
    Groups rides by nearby locations and forms cab groups by seat count and strictness.

    :param rides: List of dicts with 'lat', 'lon', 'user', etc.
    :param radius_km: float, clustering radius in kilometers
    :param group_size: int, number of bookings per cab/group
    :param strict_grouping: bool, True for only full cabs, False for max limit
    :return: List of cab groups (list of ride dicts)
    """
    # Prepare coordinates for clustering
    coords = np.array([[r['lat'], r['lon']] for r in rides])
    # DBSCAN expects radius in radians
    eps_rad = radius_km / 6371.0
    db = DBSCAN(eps=eps_rad, min_samples=1, metric='haversine').fit(np.radians(coords))
    
    # Group rides by cluster label
    clusters = {}
    for label, ride in zip(db.labels_, rides):
        clusters.setdefault(label, []).append(ride)
    
    # Form cab groups as per group_size and strict_grouping
    cab_groups = []
    for rides_in_cluster in clusters.values():
        n = len(rides_in_cluster)
        # Split into chunks of group_size
        for i in range(0, n, group_size):
            group = rides_in_cluster[i:i+group_size]
            if strict_grouping:
                if len(group) == group_size:
                    cab_groups.append(group)
            else:
                cab_groups.append(group)
    return cab_groups

# Example usage:
if __name__ == "__main__":
    # Paste your rides list here
    import random

    rides = [
        # Downtown area cluster
        {'user': 'user1', 'lat': 12.9716, 'lon': 77.5946, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user2', 'lat': 12.9720, 'lon': 77.5940, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user3', 'lat': 12.9718, 'lon': 77.5942, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user15', 'lat': 12.9716, 'lon': 77.5948, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user18', 'lat': 12.9719, 'lon': 77.5947, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user25', 'lat': 12.9714, 'lon': 77.5944, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user32', 'lat': 12.9722, 'lon': 77.5949, 'departure': '2025-10-11 18:00:00'},
        
        # Airport area cluster
        {'user': 'user4', 'lat': 13.1986, 'lon': 77.7066, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user21', 'lat': 13.1988, 'lon': 77.7062, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user28', 'lat': 13.1984, 'lon': 77.7068, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user35', 'lat': 13.1990, 'lon': 77.7064, 'departure': '2025-10-11 18:00:00'},
        
        # Electronic City cluster
        {'user': 'user5', 'lat': 12.8406, 'lon': 77.6601, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user6', 'lat': 12.8412, 'lon': 77.6605, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user16', 'lat': 12.8408, 'lon': 77.6598, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user29', 'lat': 12.8410, 'lon': 77.6603, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user36', 'lat': 12.8414, 'lon': 77.6607, 'departure': '2025-10-11 18:00:00'},
        
        # Whitefield cluster
        {'user': 'user7', 'lat': 12.9698, 'lon': 77.7500, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user8', 'lat': 12.9702, 'lon': 77.7496, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user9', 'lat': 12.9695, 'lon': 77.7503, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user17', 'lat': 12.9700, 'lon': 77.7498, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user30', 'lat': 12.9704, 'lon': 77.7502, 'departure': '2025-10-11 18:00:00'},
        
        # Koramangala cluster
        {'user': 'user10', 'lat': 12.9352, 'lon': 77.6245, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user11', 'lat': 12.9340, 'lon': 77.6250, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user12', 'lat': 12.9339, 'lon': 77.6240, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user19', 'lat': 12.9345, 'lon': 77.6253, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user31', 'lat': 12.9348, 'lon': 77.6247, 'departure': '2025-10-11 18:00:00'},
        
        # Indiranagar cluster
        {'user': 'user13', 'lat': 12.9784, 'lon': 77.6408, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user14', 'lat': 12.9788, 'lon': 77.6412, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user22', 'lat': 12.9780, 'lon': 77.6405, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user33', 'lat': 12.9786, 'lon': 77.6410, 'departure': '2025-10-11 18:00:00'},
        
        # Jayanagar cluster
        {'user': 'user20', 'lat': 12.9254, 'lon': 77.5828, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user23', 'lat': 12.9258, 'lon': 77.5825, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user26', 'lat': 12.9252, 'lon': 77.5830, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user37', 'lat': 12.9256, 'lon': 77.5827, 'departure': '2025-10-11 18:00:00'},
        
        # Malleshwaram cluster
        {'user': 'user24', 'lat': 13.0037, 'lon': 77.5744, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user27', 'lat': 13.0040, 'lon': 77.5748, 'departure': '2025-10-11 18:00:00'},
        {'user': 'user34', 'lat': 13.0035, 'lon': 77.5742, 'departure': '2025-10-11 18:00:00'},
        
        # Outer areas - scattered bookings
        {'user': 'user38', 'lat': 12.8580, 'lon': 77.6030, 'departure': '2025-10-11 18:00:00'},  # BTM Layout
        {'user': 'user39', 'lat': 13.0359, 'lon': 77.5970, 'departure': '2025-10-11 18:00:00'},  # Rajajinagar
        {'user': 'user40', 'lat': 12.9100, 'lon': 77.6400, 'departure': '2025-10-11 18:00:00'},  # HSR Layout
    ]

    random.shuffle(rides)

    print(rides)

    radius_km = 1.0          # Cluster rides within 1 km
    group_size = 4           # 4 seater cab (3 seats + driver)
    strict_grouping = False   # Only full cabs

    cab_groups = group_rides(rides, radius_km, group_size, strict_grouping)
    for idx, group in enumerate(cab_groups, 1):
        print(f"Cab Group {idx}: {[r['user'] for r in group]}")
    