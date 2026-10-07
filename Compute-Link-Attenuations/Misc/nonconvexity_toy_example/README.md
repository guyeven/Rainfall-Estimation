# A 3×3 counterexample to convexity

This example isolates the source of nonconvexity in the physical CML data-fidelity term. For one link,

$$
\widehat A(R)=\sum_{p\in\ell} d_p kR_p^\alpha,
\qquad
J_{\mathrm{atten}}(R)=\frac{(\widehat A(R)-A_{\mathrm{obs}})^2}{L}.
$$

The normalization matches `solve_rain_lbfgsb_normalized_ildw_multipliers.py` for one valid link.

## Toy link

- Grid: 3×3 pixels.
- One horizontal link crosses the three middle-row pixels.
- Each crossed segment is 0.125 km, so the link length is 0.375 km.
- Frequency: 38.003 GHz, horizontal polarization.
- Repository ITU-R P.838-3 coefficients: $k=0.400171594750$ and $\alpha=0.881535333268$.

Use two strictly positive rain fields (mm/h) that are left-right reflections of each other across the vertical centerline of the grid. In $R^{(L)}$, the heavy-rain value is in the middle-left pixel. In $R^{(R)}$, the same value is in the middle-right pixel:

$$
R^{(L)}=
\begin{bmatrix}
1&1&1\\
20&1&1\\
1&1&1
\end{bmatrix},
\qquad
R^{(R)}=
\begin{bmatrix}
1&1&1\\
1&1&20\\
1&1&1
\end{bmatrix}.
$$

Either field could be chosen as the ground truth. If $R^{(L)}$ is the ground truth, it generates the observation below, but $R^{(R)}$ produces exactly the same observation. The same statement holds with the roles reversed. The single horizontal link therefore cannot distinguish these two rain fields. Because the link crosses the reflected pixels over equal distances, their predicted attenuations are equal:

$$
\widehat A(R^{(L)})=\widehat A(R^{(R)})=A_{\mathrm{obs}}
=0.801595407171\ \mathrm{dB},
$$

and therefore both data losses are zero. Their arithmetic mean is

$$
R^{(M)}=\frac{R^{(L)}+R^{(R)}}{2}
=
\begin{bmatrix}
1&1&1\\
10.5&1&10.5\\
1&1&1
\end{bmatrix}.
$$

## Why the power law is strictly concave

To see why the power law is strictly concave, define $g(r)=r^\alpha$ for $r>0$. Its second derivative is

$$g''(r)=\alpha(\alpha-1)r^{\alpha-2}.$$

Here, $\alpha>0$, $\alpha-1<0$, and $r^{\alpha-2}>0$. Therefore, $g''(r)<0$ for every $r>0$, which means that $g$ is strictly concave. In particular,

$$\left(\frac{20+1}{2}\right)^\alpha > \frac{20^\alpha+1^\alpha}{2}.$$

In the arithmetic-mean field, the two reflected rain rates $20$ and $1$ become $10.5$ and $10.5$. The strict-concavity inequality shows that their combined attenuation contribution increases. Consequently,

$$
\widehat A(R^{(M)})=0.845082934781\ \mathrm{dB}>A_{\mathrm{obs}},
\qquad
J_{\mathrm{atten}}(R^{(M)})=0.005043106820>0.
$$

Thus

$$J_{\mathrm{atten}}\!\left(\frac{R^{(L)}+R^{(R)}}{2}\right) > \frac{J_{\mathrm{atten}}(R^{(L)})+J_{\mathrm{atten}}(R^{(R)})}{2}=0.$$

This directly violates the defining inequality for a convex function. Therefore, the physical attenuation data term is nonconvex.
