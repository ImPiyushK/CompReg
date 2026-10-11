// structs_student_records: plain aggregate structs with fixed records.
#include <cstdio>

struct Student {
    const char *name;
    int scores[3];
};

int main() {
    const Student students[] = {
        {"alice", {92, 88, 95}},
        {"bob", {61, 70, 66}},
        {"carol", {78, 83, 81}},
        {"dave", {55, 62, 58}},
    };
    constexpr int n = 4;

    long long class_total = 0;
    for (int i = 0; i < n; ++i) {
        const long long sum =
            static_cast<long long>(students[i].scores[0]) + students[i].scores[1] +
            students[i].scores[2];
        class_total += sum;
        std::printf("%s avg=%.2f sum=%lld best=%d\n", students[i].name,
                    static_cast<double>(sum) / 3.0, sum,
                    (students[i].scores[0] > students[i].scores[1]
                         ? (students[i].scores[0] > students[i].scores[2]
                                ? students[i].scores[0]
                                : students[i].scores[2])
                         : (students[i].scores[1] > students[i].scores[2]
                                ? students[i].scores[1]
                                : students[i].scores[2])));
    }
    std::printf("class_avg=%.2f\n", static_cast<double>(class_total) / static_cast<double>(n * 3));
    return 0;
}
