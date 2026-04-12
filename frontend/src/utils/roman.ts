const ROMAN_PAIRS: Array<[number, string]> = [
  [1000, 'M'],
  [900, 'CM'],
  [500, 'D'],
  [400, 'CD'],
  [100, 'C'],
  [90, 'XC'],
  [50, 'L'],
  [40, 'XL'],
  [10, 'X'],
  [9, 'IX'],
  [5, 'V'],
  [4, 'IV'],
  [1, 'I'],
];

export function toRoman(value: number | string | null | undefined): string {
  const n = typeof value === 'string' ? parseInt(value, 10) : value;
  if (n == null || !Number.isFinite(n) || n < 1 || n > 3999) {
    return value == null ? '' : String(value);
  }
  let remaining = Math.trunc(n);
  let out = '';
  for (const [arabic, roman] of ROMAN_PAIRS) {
    while (remaining >= arabic) {
      out += roman;
      remaining -= arabic;
    }
  }
  return out;
}
