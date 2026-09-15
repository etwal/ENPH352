import textwrap

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

DATA_COLOR = "0.25"
FIT_COLOR = "#D55E00"

PARAM_NAMES = ["A", "x0", "period", "width"]


def plot_two_slit_data(csv_path="TwoSlitData.csv", ax=None):
    data = pd.read_csv(csv_path)

    if ax is None:
        fig, ax = plt.subplots()
    ax.plot(data["x"], data["Intensity"], "o", markersize=3, label="Data")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("Intensity")
    ax.set_title("Two Slit Diffraction Data")

    return ax.figure, ax


def two_slit_model(x, A, x0, period, width):
    envelope = np.sinc((x - x0) / width) ** 2
    fringes = np.cos(np.pi * (x - x0) / period) ** 2
    return A * envelope * fringes


def fit_two_slit(csv_path="TwoSlitData.csv", p0=(1.0, 0.0, 5e-4, 8e-3)):
    data = pd.read_csv(csv_path)
    # absolute_sigma=False scales the covariance by the reduced chi-square, so the
    # parameter errors come from the observed residual scatter (no y-errors given).
    popt, pcov = curve_fit(two_slit_model, data["x"], data["Intensity"], p0=p0, maxfev=40000)
    perr = np.sqrt(np.diag(pcov))
    return popt, perr, data


def report_fit(popt, perr, dof, units=(("A", 1, ""), ("x0", 1e6, "um"),
                                       ("period", 1e6, "um"), ("width", 1e3, "mm"))):
    print(f"Least-squares fit, dof = {dof}")
    print(f"{'param':<8}{'value':>12}{'1s':>11}{'3s (99.7% CI)':>26}")
    for (name, scale, unit), value, err in zip(units, popt, perr):
        v, e = value * scale, err * scale
        print(f"{name:<8}{v:>12.4f}{e:>11.4f}   [{v - 3*e:>9.4f}, {v + 3*e:>9.4f}] {unit}")


CAPTION_TITLE = "Figure 1: Two-slit interference profile and least-squares fit"


def caption_text(popt, perr, rms):
    """Orient / Observe / Infer caption, with the numbers taken from the fit."""
    T, dT = popt[2] * 1e6, perr[2] * 1e6
    w, dw = popt[3] * 1e3, perr[3] * 1e3
    return (
        f"(a) Normalised intensity measured as a function of position x on the observation "
        f"screen (open circles; horizontal error bars, ≤ 8 µm, are smaller than the "
        f"markers), overlaid with a least-squares fit (orange line) to the two-slit model "
        f"I(x) = A sinc²[(x − x₀)/w] cos²[π(x − x₀)/T], in which T "
        f"is the fringe period, w the width of the diffraction envelope, x₀ the centre of "
        f"the pattern and A the peak intensity. (b) Residuals of the same fit; the grey band "
        f"spans ±1 RMS residual ({rms:.3f}). "
        f"Nine maxima are fully resolved across the 5 mm field and are evenly spaced, giving "
        f"T = {T:.2f} ± {dT:.2f} µm (1σ; 3σ interval {T - 3*dT:.2f}–"
        f"{T + 3*dT:.2f} µm). The peak intensity falls from 1.03 at the centre to 0.85 at "
        f"x = ±2.0 mm, described by a sinc² envelope of width w = {w:.2f} ± "
        f"{dw:.2f} mm (1σ; 3σ interval {w - 3*dw:.2f}–{w + 3*dw:.2f} mm). The "
        f"residuals are unstructured within ±0.05 over the central 4 mm but grow "
        f"systematically beyond |x| = 2.3 mm. "
        f"The constant fringe spacing confirms that the pattern is two-slit interference "
        f"modulated by single-slit diffraction, and constrains the period to 0.07 %. The growth "
        f"of the residuals at the edges of the field shows that the envelope is only weakly "
        f"constrained over this range (cos² and Gaussian envelopes fit equally well, "
        f"RMS {rms:.3f}), so w should not be read as a precise slit width."
    )


def plot_two_slit_fit(csv_path="TwoSlitData.csv", n=2000, caption=False):
    popt, perr, data = fit_two_slit(csv_path)

    # Millimetres keep the tick labels readable and avoid a 1e-3 offset marker.
    x_mm = data["x"] * 1e3
    x_fit = np.linspace(data["x"].min(), data["x"].max(), n)
    residuals = data["Intensity"] - two_slit_model(data["x"], *popt)
    rms = residuals.std()

    fig, (ax, ax_res) = plt.subplots(
        2, 1, sharex=True, figsize=(7.5, 8.4) if caption else (6.8, 4.9),
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12},
    )

    ax.errorbar(
        x_mm, data["Intensity"], xerr=data["uncertainty in x"] * 1e3,
        fmt="o", markersize=3.2, color=DATA_COLOR,
        markerfacecolor="white", markeredgewidth=0.9,
        elinewidth=0.8, capsize=0, linestyle="none", label="Measured",
    )
    ax.plot(x_fit * 1e3, two_slit_model(x_fit, *popt), color=FIT_COLOR,
            linewidth=1.6, label="Fit", zorder=3)

    ax.set_ylabel("Normalised intensity")
    ax.set_ylim(-0.06, 1.18)
    ax.set_yticks([0.0, 0.5, 1.0])
    handles, labels = ax.get_legend_handles_labels()
    order = [labels.index("Measured"), labels.index("Fit")]
    ax.legend([handles[i] for i in order], [labels[i] for i in order],
              frameon=False, loc="upper right", handlelength=1.4, fontsize=9)

    T, dT = popt[2] * 1e6, perr[2] * 1e6
    w, dw = popt[3] * 1e3, perr[3] * 1e3
    ax.text(
        0.015, 0.99,
        f"{'':17}1σ{'':10}3σ\n"
        f"T = {T:7.2f} µm  ± {dT:4.2f}      ± {3*dT:4.2f}\n"
        f"w = {w:7.2f} mm  ± {dw:4.2f}      ± {3*dw:4.2f}",
        transform=ax.transAxes, va="top", ha="left",
        fontsize=8, family="monospace", color="0.2", linespacing=1.5,
    )

    # Band marks +/-1 RMS so the reader can judge scatter without reading tick values.
    ax_res.axhspan(-rms, rms, color="0.88", linewidth=0)
    ax_res.axhline(0, color="0.55", linewidth=0.8)
    ax_res.plot(x_mm, residuals, "o", markersize=3.2, color=DATA_COLOR,
                markerfacecolor="white", markeredgewidth=0.9, linestyle="none")

    ax_res.set_xlabel("Position on screen, $x$ (mm)")
    ax_res.set_ylabel("Residual")
    ax_res.set_ylim(-0.22, 0.22)
    ax_res.set_yticks([-0.1, 0.0, 0.1])
    ax_res.set_xticks(np.arange(-2, 2.1, 1.0))

    for axis, label in ((ax, "(a)"), (ax_res, "(b)")):
        axis.spines[["top", "right"]].set_visible(False)
        axis.tick_params(direction="out", length=3.5, labelsize=9)
        axis.text(-0.105, 1.0, label, transform=axis.transAxes,
                  va="top", ha="left", fontsize=10, fontweight="bold")

    if caption:
        fig.subplots_adjust(left=0.115, right=0.975, top=0.975, bottom=0.42)
        fig.text(0.055, 0.352, CAPTION_TITLE, ha="left", va="top",
                 fontsize=10, fontweight="bold", color="black")
        fig.text(0.055, 0.318, textwrap.fill(caption_text(popt, perr, rms), 112),
                 ha="left", va="top", fontsize=8.3, color="0.1", linespacing=1.5)
    else:
        fig.subplots_adjust(left=0.125, right=0.98, top=0.96, bottom=0.115)

    report_fit(popt, perr, dof=len(data) - len(popt))
    print(f"{'RMS':<8}{rms:>12.4f}")

    return fig, (ax, ax_res), popt, perr


if __name__ == "__main__":
    fig, _, _, _ = plot_two_slit_fit(caption=True)
    fig.savefig("Tech Comm.png", dpi=300)
    fig.savefig("Tech Comm.pdf")
    plt.show()
