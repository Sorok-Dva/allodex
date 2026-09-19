const NUMERALS: [number, string][] = [
  [10, 'X'],
  [9, 'IX'],
  [5, 'V'],
  [4, 'IV'],
  [1, 'I'],
];

/** Chiffre romain pour n dans [1, 20] ; sinon (0 ou > 20) renvoie String(n). */
export function toRoman(n: number): string {
  if (!Number.isInteger(n) || n <= 0 || n > 20) return String(n);
  let remaining = n;
  let result = '';
  for (const [value, symbol] of NUMERALS) {
    while (remaining >= value) {
      result += symbol;
      remaining -= value;
    }
  }
  return result;
}
