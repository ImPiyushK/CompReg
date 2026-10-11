// boundary_int_limits: integer type limits and well-defined unsigned wrap.
// Signed overflow is avoided; the wrap shown is on unsigned arithmetic,
// which the standard defines.
#include <climits>
#include <cstdio>

int main() {
    std::printf("%d\n", INT_MAX);
    std::printf("%d\n", INT_MIN);
    std::printf("%u\n", UINT_MAX);
    std::printf("%lld\n", LLONG_MAX);

    // Well-defined unsigned wrap-around.
    const unsigned wrapped = 0u - 1u;
    std::printf("%u\n", wrapped);                     // UINT_MAX
    std::printf("%llu\n", static_cast<unsigned long long>(wrapped) + 1u);

    std::printf("%d\n", CHAR_BIT);
    std::printf("%zu %zu %zu\n", sizeof(short), sizeof(int), sizeof(long));
    return 0;
}
