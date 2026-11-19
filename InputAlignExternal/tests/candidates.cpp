#include "CandidatePool.hpp"
#include "Shortcut.hpp"
#include <stdexcept>
void check(bool v) { if (!v) throw std::runtime_error("candidate/shortcut invariant"); }
int main() {
    std::array<int,7> states{};
    std::array<int,7> calls{};
    auto result = iax::evaluateCandidates(states,7,4,[&](int& state,int index,int tick) {
        check(state==tick); ++state; ++calls[index];
        if(index==0) return -1; // Unsupported cannot certify a branch.
        if(index==1) return 0;
        return 1;
    });
    check(result==2 && calls[0]==1 && calls[1]==1 && calls[2]==4 && calls[6]==0);
    check(iax::evaluateCandidates(states,0,4,[](int&,int,int){return 1;})==-1);
    bool expired=false;
    try { iax::evaluateCandidates(states,7,4,[](int&,int,int)->int{throw 1;}); }
    catch(int) {expired=true;}
    check(expired);
    // Same earliest fully surviving candidate as exhaustive search, for every
    // combination of dead, unmodelled and surviving futures (3^7 cases).
    for (int pattern=0;pattern<2187;++pattern) {
        int value=pattern, expected=-1;
        std::array<int,7> outcome{};
        for (int i=0;i<7;++i) {
            outcome[i]=value%3-1; value/=3;
            if (expected<0 && outcome[i]>0) expected=i;
        }
        states.fill(0); calls.fill(0);
        int winner=iax::evaluateCandidates(states,7,400,[&](int& st,int i,int tick) {
            check(st==tick); ++st; ++calls[i];
            return tick==13 ? outcome[i] : 1;
        });
        check(winner==expected);
        for (int i=0;i<7;++i)
            check(calls[i]==(expected>=0 && i>expected ? 0 : outcome[i]>0 ? 400 : 14));
    }
    iax::Shortcut key;
    check(!key.handle(true,true,true,false).toggle);
    check(key.handle(true,true,false,true).toggle);
    check(!key.handle(true,true,true,true).toggle);
    check(key.handle(true,false,false,false).consume);
    check(key.handle(true,true,false,true).toggle);
    check(!key.handle(false,true,false,true).consume);
}
