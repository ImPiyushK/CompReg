// strings_char_ops: bounded C-string operations (no uninitialized reads).
#include <cstdio>

static size_t str_length(const char *text) {
    size_t length = 0;
    while (text[length] != '\0') {
        ++length;
    }
    return length;
}

int main() {
    char source[16] = "CompRegTest";
    char upper[16];
    char reversed[16];

    const size_t n = str_length(source);

    // Bounded copies: exactly n characters plus the terminating NUL.
    for (size_t i = 0; i < n; ++i) {
        const unsigned char c = static_cast<unsigned char>(source[i]);
        const unsigned char up = (c >= 'a' && c <= 'z') ? static_cast<unsigned char>(c - 'a' + 'A') : c;
        upper[i] = static_cast<char>(up);
        reversed[n - 1 - i] = upper[i];
    }
    upper[n] = '\0';
    reversed[n] = '\0';

    std::printf("length=%zu\n", n);
    std::printf("upper=%s\n", upper);
    std::printf("reversed=%s\n", reversed);

    // Vowel count over the uppercase copy.
    int vowels = 0;
    for (size_t i = 0; i < n; ++i) {
        if (upper[i] == 'A' || upper[i] == 'E' || upper[i] == 'I' || upper[i] == 'O' ||
            upper[i] == 'U') {
            ++vowels;
        }
    }
    std::printf("vowels=%d\n", vowels);
    return 0;
}
