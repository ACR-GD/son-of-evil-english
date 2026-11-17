// Tracing harness for ROM hacking. Usage:
// harness rom.bin frames [press s:e:btn]... [shot f:path.ppm]... [dump f:prefix]... [trace s:e:path]... [state f:path] [load path]
#include "emu.h"
#include "savestate.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <map>
extern "C" {
#include "m68k.h"
}
extern "C" void (*g_hook_r)(unsigned,int);
extern "C" void (*g_hook_w)(unsigned,unsigned,int);
static FILE* tf=nullptr; static int cur_frame=0;
static unsigned rlo=0,rhi=0,wlo=0xF00000,whi=0xF60000; // ROM read trace range
static void hr(unsigned a,int sz){ a&=0xFFFFFF; if(a>=rlo&&a<rhi) fprintf(tf,"%d R %06x %d pc=%06x\n",cur_frame,a,sz,m68k_get_reg(NULL,M68K_REG_PPC)); }
static void hw(unsigned a,unsigned v,int sz){ a&=0xFFFFFF; if((a>=wlo&&a<whi)||(a>=0xE90020&&a<0xE90040)) fprintf(tf,"%d W %06x %0*x pc=%06x\n",cur_frame,a,sz*2,v,m68k_get_reg(NULL,M68K_REG_PPC)); }
static void ppm(SuperAcan& e,const char* p){ FILE*f=fopen(p,"wb"); fprintf(f,"P6 320 240 255\n"); const uint32_t* fb=e.get_framebuffer(); for(int i=0;i<320*240;i++){uint32_t c=fb[i]; unsigned char b[3]={(unsigned char)(c>>16),(unsigned char)(c>>8),(unsigned char)c}; fwrite(b,1,3,f);} fclose(f);}
static void dump(SuperAcan& e,std::string p){ auto&b=e.get_bus(); FILE*f=fopen((p+".wram").c_str(),"wb"); fwrite(b.get_wram(),1,0x10000,f); fclose(f);
 f=fopen((p+".vram").c_str(),"wb"); for(uint32_t i=0;i<0x20000;i++){uint8_t x=b.read8(0xF40000+i); fputc(x,f);} fclose(f);
 f=fopen((p+".pal").c_str(),"wb"); for(uint32_t i=0;i<0x200;i++){fputc(b.read8(0xF00200+i),f);} fclose(f);
 f=fopen((p+".regs").c_str(),"wb"); for(uint32_t i=0;i<0x200;i++){fputc(b.read8(0xF00000+i),f);} fclose(f);}
int main(int argc,char**argv){ SuperAcan e; e.load_roms(argv[1]); int frames=atoi(argv[2]);
 struct P{int s,en;JoypadButton b;}; std::vector<P> pr; std::multimap<int,std::string> shots,dumps,states; struct T{int s,en;std::string p;}; std::vector<T> tr; std::string load;
 auto pb=[](std::string n){ if(n=="start")return BTN_START; if(n=="select")return BTN_SELECT; if(n=="a")return BTN_A; if(n=="b")return BTN_B; if(n=="x")return BTN_X; if(n=="y")return BTN_Y; if(n=="up")return BTN_UP; if(n=="down")return BTN_DOWN; if(n=="left")return BTN_LEFT; if(n=="right")return BTN_RIGHT; if(n=="l")return BTN_L; return BTN_R;};
 for(int i=3;i+1<argc;i+=2){ std::string k=argv[i], v=argv[i+1];
  if(k=="press"){int s,en;char b[16];sscanf(v.c_str(),"%d:%d:%15s",&s,&en,b);pr.push_back({s,en,pb(b)});}
  else if(k=="shot"){auto c=v.find(':');shots.insert({atoi(v.c_str()),v.substr(c+1)});}
  else if(k=="dump"){auto c=v.find(':');dumps.insert({atoi(v.c_str()),v.substr(c+1)});}
  else if(k=="state"){auto c=v.find(':');states.insert({atoi(v.c_str()),v.substr(c+1)});}
  else if(k=="load"){load=v;}
  else if(k=="wrange"){sscanf(v.c_str(),"%x:%x",&wlo,&whi);}
  else if(k=="rrange"){sscanf(v.c_str(),"%x:%x",&rlo,&rhi);}
  else if(k=="trace"){int s,en;char p[512];sscanf(v.c_str(),"%d:%d:%511s",&s,&en,p);tr.push_back({s,en,p});}}
 if(!load.empty()){ if(!SaveState::load(e,load)) fprintf(stderr,"load fail\n"); }
 for(int f=0;f<frames;f++){ cur_frame=f;
  for(auto&p:pr){ if(f==p.s)e.get_joypad().set_button(0,p.b,true); if(f==p.en)e.get_joypad().set_button(0,p.b,false);}
  for(auto&t:tr){ if(f==t.s){tf=fopen(t.p.c_str(),"w"); g_hook_w=hw; if(rhi) g_hook_r=hr;} }
  e.get_apu().clear_audio_buffer(); e.run_frame();
  for(auto&t:tr){ if(f==t.en&&tf){fclose(tf);tf=nullptr;g_hook_w=nullptr;g_hook_r=nullptr;} }
  auto r=shots.equal_range(f); for(auto it=r.first;it!=r.second;++it) ppm(e,it->second.c_str());
  r=dumps.equal_range(f); for(auto it=r.first;it!=r.second;++it) dump(e,it->second);
  r=states.equal_range(f); for(auto it=r.first;it!=r.second;++it){ SaveState::save(e,it->second);} }
 return 0; }
