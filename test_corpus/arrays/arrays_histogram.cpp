// arrays_histogram: value histogram over a fixed bounded data set.
#include <cstdio>

int main() {
    constexpr int n = 30;
    const int values[n] = {
        4, 7, 0, 2, 7, 9, 1, 4, 4, 5,
        8, 2, 7, 6, 0, 3, 3, 9, 5, 7,
        1, 4, 8, 2, 6, 9, 7, 5, 0, 4,
    };

    int counts[10] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
    for (int i = 0; i < n; ++i) {
        const int v = values[i];
        if (v >= 0 && v < 10) {
            counts[v] += 1;
        }
    }

    long long total = 0;
    for (int i = 0; i < 10; ++i) {
        std::printf("%d:%d\n", i, counts[i]);
        total += counts[i];
    }
    std::printf("%lld\n", total);  // must equal n
    return 0;
}
