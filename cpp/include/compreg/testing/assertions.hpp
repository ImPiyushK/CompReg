// compreg assertion helpers: a minimal self-checking test harness for the
// native C++ CTest suite. No third-party framework is used.
#ifndef COMPREG_TESTING_ASSERTIONS_HPP
#define COMPREG_TESTING_ASSERTIONS_HPP

#include <cstdio>
#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace compreg::testing {

struct CaseResult {
    bool ok = true;
    std::string name;
    std::string message;
};

/// Thrown by failed CHECK to short-circuit the current case body; caught by
/// the registry runner.
struct AbortCase {};

/// Registry of test cases registered by COMPREG_CASE macros in each test TU.
class Registry {
public:
    static Registry& instance() {
        static Registry registry;
        return registry;
    }

    using CaseBody = std::function<void(CaseResult&)>;

    void add(std::string name, CaseBody body) {
        cases_.emplace_back(std::move(name), std::move(body));
    }

    int run_all() const {
        int failures = 0;
        for (const auto& entry : cases_) {
            CaseResult result;
            result.name = entry.first;
            try {
                entry.second(result);
            } catch (const AbortCase&) {
                // failure already recorded by report()
            }
            std::printf("[%s] %s%s%s\n",
                        result.ok ? "PASS" : "FAIL",
                        entry.first.c_str(),
                        result.ok ? "" : " - ",
                        result.ok ? "" : result.message.c_str());
            if (!result.ok) {
                ++failures;
            }
        }
        std::printf("%zu case(s), %d failure(s)\n", cases_.size(), failures);
        return failures == 0 ? 0 : 1;
    }

private:
    std::vector<std::pair<std::string, CaseBody>> cases_;
};

/// Records a CHECK failure into the case result. `extra` may be null.
inline bool report(CaseResult& result, bool condition, const char* file, int line,
                   const char* expression, const char* extra) {
    if (condition) {
        return true;
    }
    result.ok = false;
    std::string info = std::string(expression) + " at " + file + ":" + std::to_string(line);
    if (extra != nullptr) {
        info += std::string(" (") + extra + ")";
    }
    result.message = info;
    return false;
}

}  // namespace compreg::testing

#define COMPREG_CONCAT_IMPL(a, b) a##b
#define COMPREG_CONCAT(a, b) COMPREG_CONCAT_IMPL(a, b)

#define COMPREG_CASE(name)                                                       \
    static void COMPREG_CONCAT(compreg_case_body_, __LINE__)(                    \
        ::compreg::testing::CaseResult&);                                        \
    static const bool COMPREG_CONCAT(compreg_case_registered_, __LINE__) = [] {  \
        ::compreg::testing::Registry::instance().add(                            \
            name,                                                                \
            [](::compreg::testing::CaseResult& result) {                         \
                try {                                                            \
                    COMPREG_CONCAT(compreg_case_body_, __LINE__)(result);        \
                } catch (const ::compreg::testing::AbortCase&) {                 \
                    /* failure already recorded */                               \
                }                                                                \
            });                                                                  \
        return true;                                                             \
    }();                                                                         \
    static void COMPREG_CONCAT(compreg_case_body_, __LINE__)(                    \
        ::compreg::testing::CaseResult& compreg_case_result_)

#define CHECK(expr)                                                            \
    if (!::compreg::testing::report(compreg_case_result_,                       \
                                    static_cast<bool>(expr),                    \
                                    __FILE__, __LINE__, #expr, nullptr)) {      \
        throw ::compreg::testing::AbortCase();                                  \
    }

#define CHECK_EQ(a, b)                                                          \
    if (!::compreg::testing::report(compreg_case_result_,                       \
                                    static_cast<bool>((a) == (b)),              \
                                    __FILE__, __LINE__,                        \
                                    #a " == " #b, nullptr)) {                   \
        throw ::compreg::testing::AbortCase();                                  \
    }

#endif  // COMPREG_TESTING_ASSERTIONS_HPP
