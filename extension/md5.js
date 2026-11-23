// RFC 1321 MD5 of the UTF-8 bytes of `text` as lowercase hex. Kalorické tabulky logs in with md5(password)
// and Web Crypto has no MD5.
function md5(text) {
  const bytes = new TextEncoder().encode(text);
  const words = new Uint32Array((((bytes.length + 8) >>> 6) + 1) * 16);
  bytes.forEach((byte, i) => { words[i >> 2] |= byte << ((i % 4) * 8); });
  words[bytes.length >> 2] |= 0x80 << ((bytes.length % 4) * 8);
  words[words.length - 2] = bytes.length * 8;

  const K = Array.from({ length: 64 }, (_, i) => Math.floor(Math.abs(Math.sin(i + 1)) * 2 ** 32) >>> 0);
  const SHIFTS = [7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21];
  const state = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476];

  for (let chunk = 0; chunk < words.length; chunk += 16) {
    let [a, b, c, d] = state;
    for (let i = 0; i < 64; i++) {
      let f, g;
      if (i < 16) { f = (b & c) | (~b & d); g = i; }
      else if (i < 32) { f = (d & b) | (~d & c); g = (5 * i + 1) % 16; }
      else if (i < 48) { f = b ^ c ^ d; g = (3 * i + 5) % 16; }
      else { f = c ^ (b | ~d); g = (7 * i) % 16; }
      const sum = (a + f + K[i] + words[chunk + g]) >>> 0;
      const shift = SHIFTS[(i >> 4) * 4 + (i % 4)];
      [a, d, c] = [d, c, b];
      b = (b + ((sum << shift) | (sum >>> (32 - shift)))) >>> 0;
    }
    [a, b, c, d].forEach((value, i) => { state[i] = (state[i] + value) >>> 0; });
  }
  return state.map((n) => [0, 8, 16, 24].map((s) => ((n >>> s) & 255).toString(16).padStart(2, "0")).join("")).join("");
}
