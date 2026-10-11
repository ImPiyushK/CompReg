// boundary_array_edges: first/last element access strictly inside bounds.
#include <cstdio>

int main() {
    constexpr int n = 6;
    const int data[n] = {10, 20, 30, 40, 50, 60};

    std::printf("first=%d\n", data[0]);
    std::printf("last=%d\n", data[n - 1]);

    // In-bounds forward traversal only.
    long long sum = 0;
    for (int i = 0; i < n; ++i) {
        sum += data[i];
    }
    std::printf("sum=%lld\n", sum);

    // Guarded neighbor loop: never touches indices outside [0, n).
    for (int i = 1; i < n - 1; ++i) {
        std::printf("mid:%d\n", data[i] > data[i - 1] ? data[i] : data[i - 1]);
    }
    return 0;
}
