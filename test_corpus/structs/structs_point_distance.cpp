// structs_point_distance: struct arithmetic with double fields.
// Numbers are compared via the float-list oracle with tolerance, so libm and
// printf formatting differences across platforms are not false failures.
#include <cmath>
#include <cstdio>

struct Point {
    double x;
    double y;
};

int main() {
    const Point a{0.0, 0.0};
    const Point b{3.0, 4.0};
    const Point c{-5.0, 1.5};
    const Point points[3] = {a, b, c};
    const Point *pairs[3][2] = {{&a, &b}, {&a, &c}, {&b, &c}};

    for (int k = 0; k < 3; ++k) {
        const Point &p = *pairs[k][0];
        const Point &q = *pairs[k][1];
        const double dx = p.x - q.x;
        const double dy = p.y - q.y;
        std::printf("manhattan=%.6f euclid=%.6f squared=%.6f\n",
                    std::fabs(dx) + std::fabs(dy),
                    std::sqrt(dx * dx + dy * dy),
                    dx * dx + dy * dy);
    }
    std::printf("points=%zu\n", sizeof(points) / sizeof(points[0]));
    return 0;
}
