// sorting_insertion_sort: insertion sort over a fixed 25-element array.
#include <cstdio>

int main() {
    constexpr int n = 25;
    int data[n] = {
        23, 1, 14, 8, 19, 5, 25, 11, 2, 17,
        9, 21, 4, 15, 6, 20, 12, 3, 18, 10,
        24, 7, 16, 13, 22,
    };

    for (int i = 1; i < n; ++i) {
        const int key = data[i];
        int j = i - 1;
        while (j >= 0 && data[j] > key) {
            data[j + 1] = data[j];
            --j;
        }
        data[j + 1] = key;
    }

    int sorted = 1;
    for (int i = 1; i < n; ++i) {
        if (data[i - 1] > data[i]) {
            sorted = 0;
        }
    }

    long long checksum = 0;
    for (int i = 0; i < n; ++i) {
        std::printf("%d ", data[i]);
        checksum += data[i];
    }
    std::printf("\n");
    std::printf("sorted=%d\n", sorted);
    std::printf("checksum=%lld\n", checksum);
    return 0;
}
