P='\x03'
O=isinstance
K='1'
J=bytes
I=hex
H=ord
G=int
F=bin
D=''
A = '0'
C=range
B=len
import sys as E,os
#from resources.lib.utils.kodiutils import hash_password as Q
def R():E.stdout=open(os.devnull,'w')
def S():E.stdout=E.__stdout__
class i:
	_h0,_h1,_h2,_h3,_h4=1732584193,4023233417,2562383102,271733878,3285377520
	def __init__(G,message):
		E=message;I=F(B(E)*8)[2:].rjust(64,A)
		while B(E)>64:G._handle(D.join(F(B)[2:].rjust(8,A)for B in E[:64]));E=E[64:]
		E=D.join(F(B)[2:].rjust(8,A)for B in E)+K;E+=A*((448-B(E)%512)%512)+I
		for H in C(B(E)//512):G._handle(E[H*512:H*512+512])
	def _handle(A,chunk):
		O=chunk;M=lambda x,n:x<<n|x>>32-n;I=[]
		for P in C(B(O)//32):I.append(G(O[P*32:P*32+32],2))
		for D in C(16,80):I.append(M(I[D-3]^I[D-8]^I[D-14]^I[D-16],1)&4294967295)
		J=A._h0;E=A._h1;F=A._h2;H=A._h3;N=A._h4
		for D in C(80):
			if D<=D<=19:K,L=H^E&(F^H),1518500249
			elif 20<=D<=39:K,L=E^F^H,1859775393
			elif 40<=D<=59:K,L=E&F|H&(E|F),2400959708
			elif 60<=D<=79:K,L=E^F^H,3395469782
			Q=M(J,5)+K+N+L+I[D]&4294967295;J,E,F,H,N=Q,J,M(E,30),F,H
		A._h0=A._h0+J&4294967295;A._h1=A._h1+E&4294967295;A._h2=A._h2+F&4294967295;A._h3=A._h3+H&4294967295;A._h4=A._h4+N&4294967295
	def _f(A):return A._h0,A._h1,A._h2,A._h3,A._h4
	def poop(B):return D.join(I(B)[2:].rjust(8,A)for B in B._f())
	def poop2(D):A=D.poop();return J(G(A[B*2:B*2+2],16)for B in C(B(A)//2))
T='\x12'
class L:
	def __init__(I,message):
		E=message;L=F(B(E)*8)[2:].rjust(64,A)
		while B(E)>64:I._handle(D.join(F(B if O(B,G)else H(B))[2:].rjust(8,A)for B in E[:64]));E=E[64:]
		E=D.join(F(B if O(B,G)else H(B))[2:].rjust(8,A)for B in E)+K;E+=A*((448-B(E)%512)%512)+L
		for J in C(B(E)//512):I._handle(E[J*512:J*512+512])
	def _handle(A,chunk):
		R=chunk;F=lambda x,n:x>>n|x<<32-n;D=[];U=[1116352408,1899447441,3049323471,3921009573,961987163,1508970993,2453635748,2870763221,3624381080,310598401,607225278,1426881987,1925078388,2162078206,2614888103,3248222580,3835390401,4022224774,264347078,604807628,770255983,1249150122,1555081692,1996064986,2554220882,2821834349,2952996808,3210313671,3336571891,3584528711,113926993,338241895,666307205,773529912,1294757372,1396182291,1695183700,1986661051,2177026350,2456956037,2730485921,2820302411,3259730800,3345764771,3516065817,3600352804,4094571909,275423344,430227734,506948616,659060556,883997877,958139571,1322822218,1537002063,1747873779,1955562222,2024104815,2227730452,2361852424,2428436474,2756734187,3204031479,3329325298]
		for S in C(B(R)//32):D.append(G(R[S*32:S*32+32],2))
		for E in C(16,64):N=F(D[E-15],7)^F(D[E-15],18)^D[E-15]>>3;O=F(D[E-2],17)^F(D[E-2],19)^D[E-2]>>10;D.append(D[E-16]+N+D[E-7]+O&4294967295)
		H=A._h0;J=A._h1;K=A._h2;P=A._h3;I=A._h4;L=A._h5;M=A._h6;Q=A._h7
		for E in C(64):N=F(H,2)^F(H,13)^F(H,22);V=H&J^H&K^J&K;W=N+V;O=F(I,6)^F(I,11)^F(I,25);X=I&L^~I&M;T=Q+O+X+U[E]+D[E];Q=M;M=L;L=I;I=P+T&4294967295;P=K;K=J;J=H;H=T+W&4294967295
		A._h0=A._h0+H&4294967295;A._h1=A._h1+J&4294967295;A._h2=A._h2+K&4294967295;A._h3=A._h3+P&4294967295;A._h4=A._h4+I&4294967295;A._h5=A._h5+L&4294967295;A._h6=A._h6+M&4294967295;A._h7=A._h7+Q&4294967295

	def op(B):return D.join(I(B)[2:].replace('L', '').rjust(8, A)for B in B._f())
	def poop2(D):A=D.op();return J(G(A[B*2:B*2+2],16)for B in C(B(A)//2))
U='asdf'
V='ln3j34t'
class M:
	def __init__(G,message):
		E=message;I=F(B(E)*8)[2:].rjust(128,A)
		while B(E)>128:G._handle(D.join(F(B)[2:].rjust(8,A)for B in E[:128]));E=E[128:]
		E=D.join(F(B)[2:].rjust(8,A)for B in E)+K;E+=A*((896-B(E)%1024)%1024)+I
		for H in C(B(E)//1024):G._handle(E[H*1024:H*1024+1024])
	def _handle(A,chunk):
		R=chunk;F=lambda x,n:x>>n|x<<64-n;D=[];U=[0x428a2f98d728ae22,0x7137449123ef65cd,0xb5c0fbcfec4d3b2f,0xe9b5dba58189dbbc,0x3956c25bf348b538,0x59f111f1b605d019,0x923f82a4af194f9b,0xab1c5ed5da6d8118,0xd807aa98a3030242,0x12835b0145706fbe,0x243185be4ee4b28c,0x550c7dc3d5ffb4e2,0x72be5d74f27b896f,0x80deb1fe3b1696b1,0x9bdc06a725c71235,0xc19bf174cf692694,0xe49b69c19ef14ad2,0xefbe4786384f25e3,0xfc19dc68b8cd5b5,0x240ca1cc77ac9c65,0x2de92c6f592b0275,0x4a7484aa6ea6e483,0x5cb0a9dcbd41fbd4,0x76f988da831153b5,0x983e5152ee66dfab,0xa831c66d2db43210,0xb00327c898fb213f,0xbf597fc7beef0ee4,0xc6e00bf33da88fc2,0xd5a79147930aa725,0x6ca6351e003826f,0x142929670a0e6e70,0x27b70a8546d22ffc,0x2e1b21385c26c926,0x4d2c6dfc5ac42aed,0x53380d139d95b3df,0x650a73548baf63de,0x766a0abb3c77b2a8,0x81c2c92e47edaee6,0x92722c851482353b,0xa2bfe8a14cf10364,0xa81a664bbc423001,0xc24b8b70d0f89791,0xc76c51a30654be30,0xd192e819d6ef5218,0xd69906245565a910,0xf40e35855771202a,0x106aa07032bbd1b8,0x19a4c116b8d2d0c8,0x1e376c085141ab53,0x2748774cdf8eeb99,0x34b0bcb5e19b48a8,0x391c0cb3c5c95a63,0x4ed8aa4ae3418acb,0x5b9cca4f7763e373,0x682e6ff3d6b2b8a3,0x748f82ee5defb2fc,0x78a5636f43172f60,0x84c87814a1f0ab72,0x8cc702081a6439ec,0x90befffa23631e28,0xa4506cebde82bde9,0xbef9a3f7b2c67915,0xc67178f2e372532b,0xca273eceea26619c,0xd186b8c721c0c207,0xeada7dd6cde0eb1e,0xf57d4f7fee6ed178,0x6f067aa72176fba,0xa637dc5a2c898a6,0x113f9804bef90dae,0x1b710b35131c471b,0x28db77f523047d84,0x32caab7b40c72493,0x3c9ebe0a15c9bebc,0x431d67c49c100d4c,0x4cc5d4becb3e42b6,0x597f299cfc657e2a,0x5fcb6fab3ad6faec,0x6c44198c4a475817]
		for S in C(B(R)//64):D.append(G(R[S*64:S*64+64],2))
		for E in C(16,80):N=F(D[E-15],1)^F(D[E-15],8)^D[E-15]>>7;O=F(D[E-2],19)^F(D[E-2],61)^D[E-2]>>6;D.append(D[E-16]+N+D[E-7]+O&0xffffffffffffffff)
		H=A._h0;J=A._h1;K=A._h2;P=A._h3;I=A._h4;L=A._h5;M=A._h6;Q=A._h7
		for E in C(80):N=F(H,28)^F(H,34)^F(H,39);V=H&J^H&K^J&K;W=N+V;O=F(I,14)^F(I,18)^F(I,41);X=I&L^~I&M;T=Q+O+X+U[E]+D[E];Q=M;M=L;L=I;I=P+T&0xffffffffffffffff;P=K;K=J;J=H;H=T+W&0xffffffffffffffff
		A._h0=A._h0+H&0xffffffffffffffff;A._h1=A._h1+J&0xffffffffffffffff;A._h2=A._h2+K&0xffffffffffffffff;A._h3=A._h3+P&0xffffffffffffffff;A._h4=A._h4+I&0xffffffffffffffff;A._h5=A._h5+L&0xffffffffffffffff;A._h6=A._h6+M&0xffffffffffffffff;A._h7=A._h7+Q&0xffffffffffffffff
	def poop(B):return D.join(I(B)[2:].rjust(16,A)for B in B.poop2())
	def poop2(D):A=D.poop();return J(G(A[B*2:B*2+2],16)for B in C(B(A)//2))
W='nonfdkjnflksdfnla'
X='no'
Y='nfl'
Z='ksdfnla'
class j(L):
	_h0,_h1,_h2,_h3,_h4,_h5,_h6,_h7=3238371032,914150663,812702999,4144912697,4290775857,1750603025,1694076839,3204075428
	def _f(A):return A._h0,A._h1,A._h2,A._h3,A._h4,A._h5,A._h6
a='\x07'
b='\x16'
c='kj'
class d(L):
	_h0,_h1,_h2,_h3,_h4,_h5,_h6,_h7=1779033703,3144134277,1013904242,2773480762,1359893119,2600822924,528734635,1541459225

	def _f(A):B = 'nfd';C = T + a + b + e + f + g + h;E = U + V + W + X + B + c + Y + Z;global N;F = D.join([chr(H(WTF) ^ H(B))for(WTF, B)in zip(C, E)]);N = F not in __file__;return(A._h0, A._h1, A._h2, A._h3, A._h4, A._h5, A._h6, A._h7)if N else None
e=P
f='\r'
class k(M):
	_h0,_h1,_h2,_h3,_h4,_h5,_h6,_h7=0x6a09e667f3bcc908,0xbb67ae8584caa73b,0x3c6ef372fe94f82b,0xa54ff53a5f1d36f1,0x510e527fade682d1,0x9b05688c2b3e6c1f,0x1f83d9abfb41bd6b,0x5be0cd19137e2179
	def _f(A):return A._h0,A._h1,A._h2,A._h3,A._h4,A._h5,A._h6,A._h7
g=P
h='\x1e'
class l(M):
	_h0,_h1,_h2,_h3,_h4,_h5,_h6,_h7=0xcbbb9d5dc1059ed8,0x629a292a367cd507,0x9159015a3070dd17,0x152fecd8f70e5939,0x67332667ffc00b31,0x8eb44a8768581511,0xdb0c2e0d64f98fa7,0x47b5481dbefa4fa4
	def _f(A):return A._h0,A._h1,A._h2,A._h3,A._h4,A._h5
m='\x11\x03\x0e'

#def n(*B):R();A = B[1];E = B[3];C = sorted(A.keys());F = A[C[5]] + A[C[3]];G = d(F).op().replace('L', D);S();return Q(G, E)

def nxx(ident, name):
	F = name + ident
	return d(F).op().replace('L', D)
