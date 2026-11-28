//! Powers from additions, multiplications, divisions, square roots and bit operations only, so
//! they give the same bits on every platform and in the numpy reference
//! (`terrain_pow.py`), unlike the system `pow`, whose last bit differs between C libraries.
//! ln x = k ln 2 + 2 atanh((f - 1) / (f + 1)) with f in [sqrt(1/2), sqrt(2)); exp r by its
//! Taylor series after the reduction x = k ln 2 + r (the split ln 2 of fdlibm). The error is a
//! few units in the last place, and pow(x, y) = exp(y ln x) adds |y ln x| of them.

const LN2_HI: f64 = 6.931_471_803_691_238_164_90e-01;
const LN2_LO: f64 = 1.908_214_929_270_587_700_02e-10;
const INV_LN2: f64 = 1.442_695_040_888_963_387_00e+00;
const SQRT_HALF: f64 = 0.707_106_781_186_547_524_40;
const TWO_54: f64 = 18_014_398_509_481_984.0;
const EXP_MAX: f64 = 709.782_712_893_384;
const EXP_MIN: f64 = -745.133_219_101_941_1;
pub const ATANH_TERMS: usize = 13;
pub const EXP_TERMS: usize = 17;

fn atanh_coefficients() -> [f64; ATANH_TERMS] {
    let mut found = [0.0; ATANH_TERMS];
    for (index, value) in found.iter_mut().enumerate() {
        *value = 1.0 / (2 * index + 1) as f64;
    }
    found
}

fn exp_coefficients() -> [f64; EXP_TERMS] {
    let mut found = [1.0; EXP_TERMS];
    for index in 1..EXP_TERMS {
        found[index] = found[index - 1] / index as f64;
    }
    found
}

pub fn ln(x: f64) -> f64 {
    if x.is_nan() || x < 0.0 {
        return f64::NAN;
    }
    if x == 0.0 {
        return f64::NEG_INFINITY;
    }
    if x == f64::INFINITY {
        return x;
    }
    let mut value = x;
    let mut exponent = 0i64;
    if value < f64::MIN_POSITIVE {
        value *= TWO_54;
        exponent -= 54;
    }
    let bits = value.to_bits();
    exponent += ((bits >> 52) & 0x7ff) as i64 - 1023;
    let mut fraction = f64::from_bits((bits & 0x000f_ffff_ffff_ffff) | 0x3ff0_0000_0000_0000);
    if fraction >= 2.0 * SQRT_HALF {
        fraction *= 0.5;
        exponent += 1;
    }
    let s = (fraction - 1.0) / (fraction + 1.0);
    let square = s * s;
    let coefficients = atanh_coefficients();
    let mut series = coefficients[ATANH_TERMS - 1];
    for index in (0..ATANH_TERMS - 1).rev() {
        series = series * square + coefficients[index];
    }
    let k = exponent as f64;
    k * LN2_HI + (k * LN2_LO + 2.0 * s * series)
}

pub fn exp(x: f64) -> f64 {
    if x.is_nan() {
        return x;
    }
    if x > EXP_MAX {
        return f64::INFINITY;
    }
    if x < EXP_MIN {
        return 0.0;
    }
    let k = (x * INV_LN2 + 0.5).floor();
    let r = (x - k * LN2_HI) - k * LN2_LO;
    let coefficients = exp_coefficients();
    let mut series = coefficients[EXP_TERMS - 1];
    for index in (0..EXP_TERMS - 1).rev() {
        series = series * r + coefficients[index];
    }
    scale(series, k as i64)
}

fn power_of_two(exponent: i64) -> f64 {
    f64::from_bits(((exponent + 1023) as u64) << 52)
}

fn scale(value: f64, exponent: i64) -> f64 {
    if exponent > 1023 {
        value * power_of_two(1023) * power_of_two(exponent - 1023)
    } else if exponent < -1022 {
        value * power_of_two(exponent + 1022) * power_of_two(-1022)
    } else {
        value * power_of_two(exponent)
    }
}

/// x^y for x >= 0. Exponents 1, 2, 0.5, 1.5, -1 and 0 are exact or correctly rounded.
pub fn pow(x: f64, y: f64) -> f64 {
    if y == 1.0 {
        return x;
    }
    if y == 0.0 {
        return 1.0;
    }
    if x.is_nan() || y.is_nan() || x < 0.0 {
        return f64::NAN;
    }
    if y == 2.0 {
        return x * x;
    }
    if y == 0.5 {
        return x.sqrt();
    }
    if y == 1.5 {
        return x * x.sqrt();
    }
    if y == -1.0 {
        return 1.0 / x;
    }
    if x == 0.0 {
        return if y > 0.0 { 0.0 } else { f64::INFINITY };
    }
    if x == 1.0 {
        return 1.0;
    }
    if x == f64::INFINITY {
        return if y > 0.0 { x } else { 0.0 };
    }
    exp(y * ln(x))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_the_system_functions_to_a_few_ulp() {
        let mut x = 1e-300;
        while x < 1e300 {
            let relative = (ln(x) - x.ln()).abs() / x.ln().abs().max(1e-300);
            assert!(relative < 4e-16 || (ln(x) - x.ln()).abs() < 4e-16, "ln {} {} {}", x, ln(x), x.ln());
            x *= 1.37;
        }
        let mut y = -700.0;
        while y < 700.0 {
            assert!((exp(y) / y.exp() - 1.0).abs() < 4e-15, "exp {}", y);
            y += 0.731;
        }
        for (base, exponent) in [(3.7, 0.4), (1e9, 0.5), (1e9, 0.45), (0.01, 1.3), (2.0, 10.0)] {
            assert!((pow(base, exponent) / f64::powf(base, exponent) - 1.0).abs() < 1e-14);
        }
    }
}
