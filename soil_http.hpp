// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <string>
#include <cstdlib>

namespace Soil {
// A TCP read is not an HTTP response. Accumulate bounded fragments from the
// loopback receiver, then require its exact Content-Length before trusting JSON.
template<class Read> bool receiverBody(Read read, std::string& body) {
    std::string response;char buffer[512];
    for(;;) {
        int count=read(buffer,sizeof(buffer));
        if(count<0) return false;
        if(count==0) break;
        response.append(buffer,count);
        if(response.size()>4096) return false;
    }
    auto separator=response.find("\r\n\r\n");
    if(separator==std::string::npos || response.size()<12 || response.substr(9,3)!="200") return false;
    auto header=response.find("\r\nContent-Length: ");
    if(header==std::string::npos || header>separator) return false;
    char* end=nullptr;const char* begin=response.c_str()+header+18;
    unsigned long length=strtoul(begin,&end,10);
    if(end==begin || *end!='\r' || length>4096 || length!=response.size()-separator-4) return false;
    body=response.substr(separator+4);return true;
}
}
