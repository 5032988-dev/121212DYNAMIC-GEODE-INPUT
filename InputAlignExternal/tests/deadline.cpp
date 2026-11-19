#include "../worker/branch.cpp"
#include <stdexcept>
#include <string>
void require_impl(bool ok, int line) { if (!ok) throw std::runtime_error("deadline invariant line " + std::to_string(line)); }
#define require(ok) require_impl((ok), __LINE__)
int main() {
    gd::Level level;
    level.settings.start_speed = 0.9;
    level.settings.spawn_y = 105;
    level.settings.max_gameplay_y = 100000;
    level.deadlineActive = true;
    level.deadline = std::chrono::steady_clock::now() - std::chrono::seconds(1);
    bool cancelled = false;
    try { level.timeline(-1); } catch (gd::DeadlineExceeded const&) { cancelled = true; }
    require(cancelled && level.timelines.empty());
    level.deadlineActive = false;
    auto player = gd::Simulator(level).initial_state();
    iax::Decision output{};
    int result = iax_predict_v2(&level, &player, 1, 6000, 4, 0, 0, &output);
    require((result == 0 || result == 2) && !level.deadlineActive);
    // Backoff affects speculative availability only, never unbudgeted real replay.
    int log = player.speed_log;
    level.timelineRetryAfter[log] = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    level.engine_sets=true; // Exercise the dynamic timeline query during lead replay.
    output.delay=123;
    require(iax_predict_v2(&level,&player,1,6000,4,0,0,&output)==4);
    require(output.delay==123 && !level.deadlineActive);
    level.engine_sets=false;
    level.deadlineActive = true;
    level.deadline = std::chrono::steady_clock::now() + std::chrono::seconds(1);
    cancelled = false;
    try { level.timeline(log); } catch (gd::DeadlineExceeded const&) { cancelled = true; }
    require(cancelled && level.timelines.empty());
    level.deadlineActive = false;
    require(level.timeline(log) != nullptr && level.timelineRetryAfter.count(log) == 0);
    // Standalone search shares the timeline deadline, restores callers' deadline
    // state, and never publishes the interrupted frontier.
    gd::Level search;
    search.settings = level.settings;
    auto original = std::chrono::steady_clock::now() + std::chrono::hours(1);
    search.deadline = original;
    auto resultSearch = gd::find_path(search, 10000, 100, 1, 1, 1e-12, true);
    require(!resultSearch.passed && resultSearch.inputs.empty());
    require(search.timelines.empty());
    require(!search.deadlineActive && search.deadline == original);
    search.deadlineActive = true;
    auto success = gd::find_path(search, 1, 5, 1, 1, 1., true);
    require(success.passed && !success.inputs.empty());
    require(search.deadlineActive && search.deadline == original);
    auto unlimited = gd::find_path(search, 1, 5, 1, 1, 0., true);
    require(unlimited.passed && search.deadlineActive && search.deadline == original);
    SearchOut outputSearch{};
    for (int invalid : {0, -1}) {
        require(gd_find_path(&search, 10, 1, invalid, 1, 0., 1, &outputSearch, nullptr, 0) == -1);
        require(gd_find_path(&search, 10, 1, 1, invalid, 0., 1, &outputSearch, nullptr, 0) == -1);
    }
    // Batch replay preserves the original player and catches exceptions at C ABI.
    level.deadlineActive=true;
    level.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    auto originalTick=player.tick;
    require(gd_replay(&level,&player,0,64)==nullptr && player.tick==originalTick);
    require(gd_replay(&level,&player,0,65)==nullptr);
    level.deadlineActive=false;
    auto replayed=static_cast<gd::Player*>(gd_replay(&level,&player,0,64));
    require(replayed && replayed->tick==originalTick+64 && player.tick==originalTick);
    gd_state_free(replayed);
    // A cancelled query must not leave a deadline active across the C ABI replay call.
    auto next = gd::Simulator(level).step(player, false);
    require(next.tick == 1);
}
