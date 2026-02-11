import matplotlib.pyplot as plt
from alpha_shapes import Alpha_Shaper, plot_alpha_shape
import gpx

f = gpx.read_gpx("activity_21804056192.gpx")
points = [(float(p.lat), float(p.lon)) for p in f.trk[0].trkseg[0].trkpt]

# shaper = Alpha_Shaper(points)
#
# # Calculate the shape
# alpha = 3.0
# alpha_shape = shaper.get_shape(alpha=alpha)
#
# fig, (ax0, ax1) = plt.subplots(1, 2)
# ax0.scatter(*zip(*points))
# ax0.set_title('data')
# ax1.scatter(*zip(*points))
# plot_alpha_shape(ax1, alpha_shape)
# ax1.set_title(f"$\\alpha={alpha:.3}$")
#
# for ax in (ax0, ax1):
#     ax.set_aspect('equal')
#
# # Calculate the shape with increased alpha value
# alpha = 4.5
# alpha_shape = shaper.get_shape(alpha=alpha)
#
# fig, (ax0, ax1) = plt.subplots(1, 2)
# ax0.scatter(*zip(*points))
# ax0.set_title('data')
# ax1.scatter(*zip(*points))
# plot_alpha_shape(ax1, alpha_shape)
# ax1.set_title(f"$\\alpha={alpha:.3}$")
#
# for ax in (ax0, ax1):
#     ax.set_aspect('equal')
#
# # Calculate the optimal alpha shape
# alpha_opt, alpha_shape = shaper.optimize()
# print(alpha_opt)
#
# fig, (ax0, ax1) = plt.subplots(1, 2)
# ax0.scatter(*zip(*points))
# ax0.set_title('data')
# ax1.scatter(*zip(*points))
# plot_alpha_shape(ax1, alpha_shape)
# ax1.set_title(f"$\\alpha_{{\\mathrm{{opt}}}}={alpha_opt:.3}$")
#
# for ax in (ax0, ax1):
#     ax.set_aspect('equal')
#
# plt.show()

from math import radians, cos, sin, asin, sqrt


def get_distance(p1, p2):
    lat1, lon1 = p1
    lat2, lon2 = p2

    ##convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    ##haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))
    # Radius of earth in kilometers. Use 3956 for miles
    r = 6371
    return c * r


filtered = [points[0]]

i = 0
while i < (len(points) - 1):
    for j in range(i + 1, len(points)):
        dist = get_distance(points[i], points[j])
        if dist > 0.01:  # km
            filtered += [points[j]]
            break
    i = j

print("\n".join([f"{{ lat: {a}, lng: {b}, name: '' }}," for a, b in filtered]))
