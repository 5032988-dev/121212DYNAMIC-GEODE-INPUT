// Copyright (c) 2026 dadjdjxjfjdjd-sketch. SPDX-License-Identifier: MIT
#include "../worker/branch.cpp"
#include <iostream>
#define CHECK(x) do { if (!(x)) { std::cerr << "Failed: " #x " line " << __LINE__ << '\n'; return 1; } } while(false)
int main() {
    using namespace gd;
    Level level;
    int log = level.logs.append(-1, {0, 0., 1.});
    Trigger move{}; move.kind = MOVE; move.target = 5; move.dx = 100; move.duration = 1.; move.rate = 2.;
    Trigger stop{}; stop.kind = STOP; stop.target = 5; stop.x = 60;
    Trigger later = stop; later.x = 120;
    level.triggers = {move, stop, later}; level.finish_engine();
    CHECK(level.timeline(log)->moves.at(5).front().stop == 60);
    Obj a{}; a.index = 0; a.cat = C_HAZARD; a.x = 100; a.x0 = 95; a.x1 = 105;
    Obj b = a; b.index = 1; b.x = 500; b.x0 = 495; b.x1 = 505;
    level.objects = {a, b};
    GroupSet group{}; group.always = true; group.objects = {0, 1};
    level.sets = {group}; level.finish_engine();
    std::vector<Obj const*> first, second;
    level.dynamic_near(log, 1, 80, 120, first);
    level.dynamic_near(log, 1, 480, 520, second);
    CHECK(first.size() == 1 && first[0]->x == 100);
    CHECK(second.size() == 1 && second[0]->x == 500);
    // The second query must not invalidate pointers held by the first collision query.
    CHECK(first[0]->x == 100);
    Level loop;
    log = loop.logs.append(-1, {0, 0., 1.});
    Trigger spawn{}; spawn.kind = SPAWN; spawn.target = 7; spawn.groups = {7};
    loop.triggers = {spawn}; loop.finish_engine();
    CHECK(loop.timeline(log)->truncated);
    CHECK(loop.unsupported.count("spawn loop cut") == 1);
    loop.unsupported.clear(); second.clear();
    loop.dynamic_near(log, 1, 0, 10, second);
    CHECK(loop.unsupported.count("spawn loop cut") == 1);
    Level consumed;
    consumed.settings.start_speed = .9; consumed.settings.spawn_y = 105; consumed.settings.max_gameplay_y = 2800;
    a.index = 0; a.indexed = false; consumed.objects = {a};
    Simulator sim(consumed); auto p = sim.initial_state(); p.x = 500; p.activated = {0};
    p = sim.step(p, false);
    CHECK(p.activated.size() == 1 && p.activated[0] == 0);
    // No fixed list ceiling: summaries remain cheap and full inspection can fetch all IDs.
    p.activated.resize(129);
    for (int i=0;i<129;++i) p.activated[i]=i;
    StateView view{};
    CHECK(gd_state_view(&consumed,&p,&view,1) == 1);
    CHECK(gd_state_view(&consumed,&p,&view,0) == 0);
    CHECK(gd_state_list(&consumed,&p,1,nullptr,0) == 129);
    std::vector<int> ids(129);
    CHECK(gd_state_list(&consumed,&p,1,ids.data(),129) == 129 && ids.back() == 128);
    Level dense;
    log=dense.logs.append(-1,{0,0.,1.});
    for (int i=0;i<10000;++i) dense.triggers.push_back(move);
    stop.x=0;
    for (int i=0;i<10000;++i) dense.triggers.push_back(stop);
    stop.x=60; dense.triggers.push_back(stop);
    for (int i=0;i<10000;++i) dense.triggers.push_back(stop);
    dense.finish_engine();
    CHECK(dense.timeline(log)->moves.at(5).size()==10000);
    CHECK(dense.timeline(log)->moves.at(5).back().stop==60);
    // Exceeding the cache cap must keep recently used exact timelines alive.
    Level cached; cached.settings = consumed.settings;
    std::vector<int> logs;
    for (int i=0;i<65;++i) {
        int id=cached.logs.append(-1,{0,double(i),1.});
        logs.push_back(id); cached.timeline(id);
    }
    cached.timeline(logs.front()); // Touch the oldest key: it is now recently used.
    auto retained=cached.timelines.at(logs.front());
    auto cachedPlayer=Simulator(cached).initial_state();
    auto replay=Simulator(cached).step(cachedPlayer,false);
    CHECK(replay.tick==1);
    CHECK(cached.timelines.size()>=64);
    CHECK(cached.timelines.count(logs.front())==1);
    CHECK(cached.timelines.at(logs.front())==retained);
    CHECK(cached.timelines.count(logs[1])==0);
    for (double delay : {-1., std::numeric_limits<double>::infinity(), 1e100, 1.}) {
        Level invalid; Trigger child{}; child.kind=SPAWN; child.delay=delay;
        invalid.triggers={child}; invalid.finish_engine();
        int badLog=invalid.logs.append(-1,{std::numeric_limits<long long>::max()-2,0.,1.});
        CHECK(invalid.timeline(badLog)->truncated);
        CHECK(invalid.unsupported.count("spawn timing out of range")==1);
    }
    // Contacts and prior-contact IDs refer to world sides, independent of gravity.
    Obj block{}; block.index = 42; block.y0 = 150; block.y1 = 180;
    for (bool inverted : {false, true}) {
        for (bool top : {false, true}) {
            auto ship = sim.initial_state(); ship.mode = SHIP; ship.upside_down = inverted;
            ship.y = ship.prev_y = top ? block.y0 - ship.width()/2 : block.y1 + ship.width()/2;
            ship.y_vel = top ? 1 : -1;
            StepContacts contact;
            sim.collide_solid(ship, block, contact);
            CHECK((top ? contact.top_uid : contact.bottom_uid) == 42);
            CHECK((top ? contact.bottom_uid : contact.top_uid) == -1);
        }
    }
    // A previous world-top contact keeps an inverted ship attached even in deep overlap.
    auto ship = sim.initial_state(); ship.mode = SHIP; ship.upside_down = true;
    ship.y = ship.prev_y = block.y0; ship.y_vel = 1; ship.prev_top_uid = 42;
    StepContacts contact;
    sim.collide_solid(ship, block, contact);
    CHECK(contact.top_uid == 42 && !ship.dead);
    return 0;
}
