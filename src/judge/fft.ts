export function nextPowerOfTwo(value: number): number {
  let size = 1;
  while (size < value) size *= 2;
  return size;
}

export function fft(real: Float64Array, imaginary: Float64Array, inverse = false): void {
  const n = real.length;
  for (let index = 1, swapped = 0; index < n; index += 1) {
    let bit = n >> 1;
    for (; swapped & bit; bit >>= 1) swapped ^= bit;
    swapped ^= bit;
    if (index < swapped) {
      [real[index], real[swapped]] = [real[swapped]!, real[index]!];
      [imaginary[index], imaginary[swapped]] = [imaginary[swapped]!, imaginary[index]!];
    }
  }
  for (let length = 2; length <= n; length *= 2) {
    const angle = ((inverse ? 2 : -2) * Math.PI) / length;
    const stepReal = Math.cos(angle);
    const stepImaginary = Math.sin(angle);
    const half = length / 2;
    for (let start = 0; start < n; start += length) {
      let turnReal = 1;
      let turnImaginary = 0;
      for (let offset = 0; offset < half; offset += 1) {
        const even = start + offset;
        const odd = even + half;
        const oddReal = real[odd]! * turnReal - imaginary[odd]! * turnImaginary;
        const oddImaginary = real[odd]! * turnImaginary + imaginary[odd]! * turnReal;
        real[odd] = real[even]! - oddReal;
        imaginary[odd] = imaginary[even]! - oddImaginary;
        real[even] = real[even]! + oddReal;
        imaginary[even] = imaginary[even]! + oddImaginary;
        const nextReal = turnReal * stepReal - turnImaginary * stepImaginary;
        turnImaginary = turnReal * stepImaginary + turnImaginary * stepReal;
        turnReal = nextReal;
      }
    }
  }
  if (inverse) {
    for (let index = 0; index < n; index += 1) {
      real[index] = real[index]! / n;
      imaginary[index] = imaginary[index]! / n;
    }
  }
}

function transformRows(real: Float64Array, imaginary: Float64Array, width: number, height: number, inverse: boolean): void {
  const rowReal = new Float64Array(width);
  const rowImaginary = new Float64Array(width);
  for (let y = 0; y < height; y += 1) {
    const start = y * width;
    rowReal.set(real.subarray(start, start + width));
    rowImaginary.set(imaginary.subarray(start, start + width));
    fft(rowReal, rowImaginary, inverse);
    real.set(rowReal, start);
    imaginary.set(rowImaginary, start);
  }
}

function transformColumns(real: Float64Array, imaginary: Float64Array, width: number, height: number, inverse: boolean): void {
  const columnReal = new Float64Array(height);
  const columnImaginary = new Float64Array(height);
  for (let x = 0; x < width; x += 1) {
    for (let y = 0; y < height; y += 1) {
      columnReal[y] = real[y * width + x]!;
      columnImaginary[y] = imaginary[y * width + x]!;
    }
    fft(columnReal, columnImaginary, inverse);
    for (let y = 0; y < height; y += 1) {
      real[y * width + x] = columnReal[y]!;
      imaginary[y * width + x] = columnImaginary[y]!;
    }
  }
}

export function fft2(real: Float64Array, imaginary: Float64Array, width: number, height: number, inverse = false): void {
  transformRows(real, imaginary, width, height, inverse);
  transformColumns(real, imaginary, width, height, inverse);
}

export function circularAutocorrelation(values: Float64Array, width: number, height: number): Float64Array {
  const real = Float64Array.from(values);
  const imaginary = new Float64Array(values.length);
  fft2(real, imaginary, width, height);
  for (let index = 0; index < real.length; index += 1) {
    real[index] = real[index]! * real[index]! + imaginary[index]! * imaginary[index]!;
    imaginary[index] = 0;
  }
  fft2(real, imaginary, width, height, true);
  return real;
}
