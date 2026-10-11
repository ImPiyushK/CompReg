// sorting_binary_search: search every target, reporting index or -1.
#include <cstdio>

int main() {
    constexpr int n = 10;
    const int sorted[n] = {2, 5, 8, 12, 16, 23, 38, 56, 72, 91};
    const int targets[] = {2, 23, 91, 4, 100, 8, 0, 72};
    constexpr int t = 8;

    for (int k = 0; k < t; ++k) {
        int low = 0;
        int high = n - 1;
        int found = -1;
        while (low <= high) {
            const int mid = low + (high - low) / 2;
            if (sorted[mid] == targets[k]) {
                found = mid;
                break;
            } else if (sorted[mid] < targets[k]) {
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        std::printf("%d:%d\n", targets[k], found);
    }
    return 0;
}
