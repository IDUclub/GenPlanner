mod loss_topo;
use del_candle::voronoi2::VoronoiInfo;
use del_canvas_core::canvas_gif::Canvas;
use pyo3::prelude::*;
use std::panic;

#[pyfunction]
fn optimize_space(
    vtxl2xy: Vec<f32>,
    site2xy: Vec<f32>,
    site2room: Vec<usize>,
    site2xy2flag: Vec<f32>,
    room2area_trg: Vec<f32>,
    room_connections: Vec<(usize, usize)>,
    create_gif: bool,
) -> PyResult<(Vec<usize>, Vec<usize>, Vec<f32>, Vec<usize>)> {
    let result = panic::catch_unwind(|| {
        optimize(
            vtxl2xy,
            site2xy,
            site2room,
            site2xy2flag,
            room2area_trg,
            room_connections,
            create_gif,
        )
    });
    match result {
        Ok(Ok(value)) => Ok(value),
        Ok(Err(e)) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            e.to_string(),
        )),
        Err(panic_info) => {
            let panic_message = if let Some(s) = panic_info.downcast_ref::<&str>() {
                s.to_string()
            } else if let Some(s) = panic_info.downcast_ref::<String>() {
                s.clone()
            } else {
                "Unknown panic occurred".to_string()
            };
            Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(panic_message))
        }
    }
}

#[pymodule]
fn rust_optimizer(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(optimize_space, m)?)?;
    Ok(())
}


pub fn my_paint(
    canvas: &mut Canvas,
    transform_to_scr: &nalgebra::Matrix3<f32>,
    vtxl2xy: &[f32],
    site2xy: &[f32],
    voronoi_info: &VoronoiInfo,
    vtxv2xy: &[f32],
    site2room: &[usize],
    edge2vtxv_wall: &[usize],
) {
    let site2idx = &voronoi_info.site2idx;
    let idx2vtxv = &voronoi_info.idx2vtxv;
    //
    for i_site in 0..site2idx.len() - 1 {
        let i_room = site2room[i_site];
        if i_room == usize::MAX {
            continue;
        }
        //
        let i_color: u8 = if i_room == usize::MAX {
            1
        } else {
            (i_room + 2).try_into().unwrap()
        };
        //
        let num_vtx_in_site = site2idx[i_site + 1] - site2idx[i_site];
        if num_vtx_in_site == 0 { continue; }
        let mut vtx2xy = vec!(0f32; num_vtx_in_site * 2);
        for i_vtx in 0..num_vtx_in_site {
            let i_vtxv = idx2vtxv[site2idx[i_site] + i_vtx];
            vtx2xy[i_vtx * 2 + 0] = vtxv2xy[i_vtxv * 2 + 0];
            vtx2xy[i_vtx * 2 + 1] = vtxv2xy[i_vtxv * 2 + 1];
        }
        del_canvas_core::rasterize_polygon::fill(
            &mut canvas.data, canvas.width,
            &vtx2xy, arrayref::array_ref![transform_to_scr.as_slice(),0,9], i_color)
    }
    // draw points;
    for i_site in 0..site2xy.len() / 2 {
        let i_room = site2room[i_site];
        if i_room == usize::MAX {
            continue;
        }
        if i_room == usize::MAX {
            1
        } else {
            (i_room + 2).try_into().unwrap()
        };
        del_canvas_core::rasterize_circle::fill(
            &mut canvas.data,
            canvas.width,
            &[site2xy[i_site * 2 + 0], site2xy[i_site * 2 + 1]],
            arrayref::array_ref![transform_to_scr.as_slice(),0,9],
            2.0,
            1,
        );
    }
    // draw cell boundary
    for i_site in 0..site2idx.len() - 1 {
        let num_vtx_in_site = site2idx[i_site + 1] - site2idx[i_site];
        for i0_vtx in 0..num_vtx_in_site {
            let i1_vtx = (i0_vtx + 1) % num_vtx_in_site;
            let i0 = idx2vtxv[site2idx[i_site] + i0_vtx];
            let i1 = idx2vtxv[site2idx[i_site] + i1_vtx];
            del_canvas_core::rasterize_line::draw_dda_with_transformation(
                &mut canvas.data,
                canvas.width,
                &[vtxv2xy[i0 * 2 + 0], vtxv2xy[i0 * 2 + 1]],
                &[vtxv2xy[i1 * 2 + 0], vtxv2xy[i1 * 2 + 1]],
                arrayref::array_ref![transform_to_scr.as_slice(),0,9],
                1,
            );
        }
    }
    // draw room boundary
    for i_edge in 0..edge2vtxv_wall.len() / 2 {
        let i0_vtxv = edge2vtxv_wall[i_edge * 2 + 0];
        let i1_vtxv = edge2vtxv_wall[i_edge * 2 + 1];
        del_canvas_core::rasterize_line::draw_pixcenter(
            &mut canvas.data,
            canvas.width,
            &[vtxv2xy[i0_vtxv * 2 + 0], vtxv2xy[i0_vtxv * 2 + 1]],
            &[vtxv2xy[i1_vtxv * 2 + 0], vtxv2xy[i1_vtxv * 2 + 1]],
            arrayref::array_ref![transform_to_scr.as_slice(), 0, 9],
            1.1,
            1,
        );
    }
    del_canvas_core::rasterize_polygon::stroke(
        &mut canvas.data,
        canvas.width,
        &vtxl2xy,
        arrayref::array_ref![transform_to_scr.as_slice(),0,9],
        1.1,
        1,
    );
}

pub fn edge2vtvx_wall(voronoi_info: &VoronoiInfo, site2room: &[usize]) -> Vec<usize> {
    let site2idx = &voronoi_info.site2idx;
    let idx2vtxv = &voronoi_info.idx2vtxv;
    let mut edge2vtxv = vec![0usize; 0];
    // get wall between rooms
    for i_site in 0..site2idx.len() - 1 {
        let i_room = site2room[i_site];
        if i_room == usize::MAX {
            continue;
        }
        let num_vtx_in_site = site2idx[i_site + 1] - site2idx[i_site];
        for i0_vtx in 0..num_vtx_in_site {
            let i1_vtx = (i0_vtx + 1) % num_vtx_in_site;
            let idx = site2idx[i_site] + i0_vtx;
            let i0_vtxv = idx2vtxv[idx];
            let i1_vtxv = idx2vtxv[site2idx[i_site] + i1_vtx];
            let j_site = voronoi_info.idx2site[idx];
            if j_site == usize::MAX {
                continue;
            }
            if i_site >= j_site {
                continue;
            }
            let j_room = site2room[j_site];
            if i_room == j_room {
                continue;
            }
            edge2vtxv.push(i0_vtxv);
            edge2vtxv.push(i1_vtxv);
        }
    }
    edge2vtxv
}

pub fn room2area(
    site2room: &[usize],
    num_room: usize,
    site2idx: &[usize],
    idx2vtxv: &[usize],
    vtxv2xy: &candle_core::Tensor,
) -> candle_core::Result<candle_core::Tensor> {
    let polygonmesh2_to_areas = del_candle::polygonmesh2_to_areas::Layer {
        elem2idx: Vec::<usize>::from(site2idx),
        idx2vtx: Vec::<usize>::from(idx2vtxv),
    };
    let site2areas = vtxv2xy.apply_op1(polygonmesh2_to_areas)?;
    let site2areas = site2areas.reshape((site2areas.dim(0).unwrap(), 1))?; // change shape to use .mutmul()
    //
    let num_site = site2room.len();
    let sum_sites_for_rooms = {
        let mut sum_sites_for_rooms = vec![0f32; num_site * num_room];
        for i_site in 0..num_site {
            let i_room = site2room[i_site];
            if i_room == usize::MAX {
                continue;
            }
            assert!(i_room < num_room);
            sum_sites_for_rooms[i_room * num_site + i_site] = 1f32;
        }
        candle_core::Tensor::from_slice(
            &sum_sites_for_rooms,
            candle_core::Shape::from((num_room, num_site)),
            &candle_core::Device::Cpu,
        )?
    };
    sum_sites_for_rooms.matmul(&site2areas)
}
pub fn optimize(
    vtxl2xy: Vec<f32>,
    site2xy: Vec<f32>,
    site2room: Vec<usize>,
    site2xy2flag: Vec<f32>,
    room2area_trg: Vec<f32>,
    room_connections: Vec<(usize, usize)>,
    create_gif: bool)
    -> anyhow::Result<(Vec<usize>, Vec<usize>, Vec<f32>, Vec<usize>)>
{
    let mut final_vtxv2xy = Vec::new();
    let mut final_site2idx = Vec::new();
    let mut final_idx2vtxv = Vec::new();
    let mut final_edge2vtxv_wall = Vec::new();

    let fixed_flags = site2xy2flag.iter().filter(|&&x| x != 0.0).count();

    let room2color = vec![
        0xAEC6CF,  // Пастельно-голубой
        0xC7F0BD,  // Пастельно-зеленый
        0xC9A0DC,  // Пастельно-фиолетовый
        0xFF9AA2,  // Пастельно-красный
        0xB5EAD7,  // Пастельно-бирюзовый
        0xFFFACD,  // Пастельно-желтый (более светлый)
        0xFFB347,  // Пастельно-оранжевый (немного ярче для различимости)
        0xF8B7D8   // Пастельно-розовый (вместо пурпурного)
    ];
    let gif_size = (500, 500);
    let mut canvas_gif = if create_gif {
        let num_room = room2area_trg.len();
        let mut palette = vec![0xffffff, 0x000000];
        for i_room in 0..num_room {
            palette.push(room2color[i_room]);
        }
        Some(Canvas::new("./test.gif", gif_size, &palette))
    } else {
        None
    };

    let transform_world2pix = nalgebra::Matrix3::<f32>::new(
        gif_size.0 as f32 * 0.8,
        0.,
        gif_size.0 as f32 * 0.1,
        0.,
        -(gif_size.1 as f32) * 0.8,
        gif_size.1 as f32 * 0.9,
        0.,
        0.,
        1.,
    );
    // ---------------------
    // candle from here
    let site2xy = candle_core::Var::from_slice(
        &site2xy,
        candle_core::Shape::from((site2xy.len() / 2, 2)),
        &candle_core::Device::Cpu,
    ).unwrap();
    let site2xy2flag = candle_core::Var::from_slice(
        &site2xy2flag,
        candle_core::Shape::from((site2xy2flag.len() / 2, 2)),
        &candle_core::Device::Cpu,
    ).unwrap();
    let site2xy_ini = candle_core::Tensor::from_vec(
        site2xy.flatten_all().unwrap().to_vec1::<f32>()?,
        candle_core::Shape::from((site2xy.dims2()?.0, 2)),
        &candle_core::Device::Cpu,
    ).unwrap();
    assert_eq!(site2room.len(), site2xy.dims2()?.0);
    //
    let room2area_trg = {
        let num_room = room2area_trg.len();
        candle_core::Tensor::from_vec(
            room2area_trg,
            candle_core::Shape::from((num_room, 1)),
            &candle_core::Device::Cpu,
        )
            .unwrap()
    };
    let adamw_params = candle_nn::ParamsAdamW {
        lr: 0.2,
        ..Default::default()
    };

    use candle_nn::Optimizer;
    let mut optimizer = candle_nn::AdamW::new(vec![site2xy.clone()], adamw_params)?;
    let n_sites = site2room.len();
    let base_iter = 250;
    let max_iter = 600;
    let mut n_iter = base_iter + ((n_sites.saturating_sub(10) * (max_iter - base_iter)) / 50);

    if fixed_flags > 0 {
        n_iter = (n_iter as f32 * 1.1).round() as usize;
    }

    let warmup_iters = n_iter / 20;
    let max_lr = 0.08;
    let min_lr = 0.005;
    let decay_start = n_iter / 6;

    for _iter in 0..n_iter {

        let current_lr = if _iter < warmup_iters {
            0.02 + (max_lr - 0.02) * (_iter as f32 / warmup_iters as f32)
        } else if _iter < decay_start {
            max_lr
        } else {
            let decay_progress = (_iter - decay_start) as f32 / (n_iter - decay_start) as f32;
            min_lr + 0.5 * (max_lr - min_lr) * (1.0 + f32::cos(std::f32::consts::PI * decay_progress))
        };

        optimizer.set_params(candle_nn::ParamsAdamW {
            lr: current_lr as f64,
            beta2: 0.95,
            ..Default::default()
        });

        let (vtxv2xy, voronoi_info)
            = del_candle::voronoi2::voronoi(&vtxl2xy, &site2xy, |i_site| {
            site2room[i_site] != usize::MAX
        });
        let edge2vtxv_wall = crate::edge2vtvx_wall(&voronoi_info, &site2room);

        // let loss_lloyd_internal = floorplan::loss_lloyd_internal(&voronoi_info, &site2room, &site2xy, &vtxv2xy)?;
        let (loss_each_area, loss_total_area) = {
            let room2area = crate::room2area(
                &site2room,
                room2area_trg.dims2()?.0,
                &voronoi_info.site2idx,
                &voronoi_info.idx2vtxv,
                &vtxv2xy,
            )?;
            /*
            {
                let room2area = room2area.flatten_all()?.to_vec1::<f32>()?;
                let total_area = del_msh::polyloop2::area_(&vtxl2xy);
                for i_room in 0..room2area.len() {
                    println!("    room:{} area:{}", i_room, room2area[i_room]/total_area);
                }
            }
             */
            let loss_each_area = room2area.sub(&room2area_trg)?.sqr()?.sum_all()?;
            let total_area_trg = del_msh_core::polyloop2::area_(&vtxl2xy);
            let total_area_trg = candle_core::Tensor::from_vec(
                vec![total_area_trg],
                candle_core::Shape::from(()),
                &candle_core::Device::Cpu,
            )?;
            let loss_total_area = (room2area.sum_all()? - total_area_trg)?.abs()?;
            (loss_each_area, loss_total_area)
        };
        // println!("  loss each_area {}", loss_each_area.to_vec0::<f32>()?);
        // println!("  loss total_area {}", loss_total_area.to_vec0::<f32>()?);
        let loss_walllen = {
            let vtx2xyz_to_edgevector = del_candle::vtx2xyz_to_edgevector::Layer {
                edge2vtx: Vec::<usize>::from(edge2vtxv_wall.clone()),
            };
            let edge2xy = vtxv2xy.apply_op1(vtx2xyz_to_edgevector)?;
            edge2xy.abs()?.sum_all()?
            //edge2xy.sqr()?.sum_all()?
        };
        let loss_topo = loss_topo::unidirectional(
            &site2xy,
            // &site2xy_ini,
            // &site2xy2flag,
            &site2room,
            room2area_trg.dims2()?.0,
            &voronoi_info,
            &room_connections,
        )?;
        // println!("  loss topo: {}", loss_topo.to_vec0::<f32>()?);
        // let loss_fix = site2xy.sub(&site2xy_ini)?.mul(&site2xy2flag)?.sum_all()?;
        // let loss_fix = site2xy.sub(&site2xy_ini)?.mul(&site2xy2flag)?.sum_all()?;

        let loss_fix = site2xy.sub(&site2xy_ini)?.mul(&site2xy2flag)?.sqr()?.sqr()?.sum_all()?;

        let loss_lloyd = del_candle::voronoi2::loss_lloyd(
            &voronoi_info.site2idx, &voronoi_info.idx2vtxv,
            &site2xy, &vtxv2xy)?;
        // dbg!(loss_fix.to_vec0::<f32>()?);
        // ---------
        /*
        let loss_each_area = if _iter > 150 {
            loss_each_area.affine(5.0, 0.0)?.clone()
        }
        else {
        };
         */
        let topo_weight = if _iter < decay_start {
            10.0 + (_iter as f32 / decay_start as f32) * 150.0
        } else {
            150.0
        };

        // TODO Кароче надо loss fix накручивать на все точки одного полигона (как делать? - хз)

        let loss_each_area = loss_each_area.affine(50000.0, 0.0)?.clone();
        let loss_total_area = loss_total_area.affine(10000.0, 0.0)?.clone();
        let loss_walllen = loss_walllen.affine(20.0, 0.0)?;
        let loss_topo = loss_topo.affine(topo_weight as f64, 0.0)?;
        let loss_fix = loss_fix.affine(10000000., 0.0)?;
        let loss_lloyd = loss_lloyd.affine(0.1, 0.0)?;
        // dbg!(loss_fix.flatten_all()?.to_vec1::<f32>());

        // let loss_fix_topo = loss_fix.mul(&loss_topo)?.affine(0.01, 0.)?;


        {
            use std::io::Write;
            let file = std::fs::OpenOptions::new().write(true).append(true).create(true).open("conv.csv")?;
            let mut writer = std::io::BufWriter::new(&file);
            writeln!(&mut writer, "{}, {},{},{},{},{},{},{}",
                     _iter,
                     loss_each_area.clone().to_vec0::<f32>()?,
                     loss_total_area.clone().to_vec0::<f32>()?,
                     loss_walllen.clone().to_vec0::<f32>()?,
                     loss_topo.clone().to_vec0::<f32>()?,
                     loss_fix.clone().to_vec0::<f32>()?,
                     loss_lloyd.clone().to_vec0::<f32>()?,
                     // loss_fix_topo.clone().to_vec0::<f32>()?,
                     current_lr,
            ).expect("TODO: panic message");
        }

        let loss = (
            loss_each_area
                + loss_total_area
                + loss_walllen
                + loss_topo
                + loss_fix
                + loss_lloyd
            // + loss_fix_topo
        )?;

        // println!("  loss: {}", loss.to_vec0::<f32>()?);
        optimizer.backward_step(&loss)?;
        // ----------------
        // visualization
        if let Some(canvas_gif) = &mut canvas_gif {
            canvas_gif.clear(0);
            crate::my_paint(
                canvas_gif,
                &transform_world2pix,
                &vtxl2xy,
                &site2xy.flatten_all()?.to_vec1::<f32>()?,
                &voronoi_info,
                &vtxv2xy.flatten_all()?.to_vec1::<f32>()?,
                &site2room,
                &edge2vtxv_wall,
            );
            canvas_gif.write();
        }
        if _iter == n_iter - 1 {
            final_site2idx = voronoi_info.site2idx;
            final_idx2vtxv = voronoi_info.idx2vtxv;
            final_vtxv2xy = vtxv2xy.flatten_all()?.to_vec1::<f32>()?;
            final_edge2vtxv_wall = edge2vtxv_wall.clone();
        }
    }
    Ok((final_site2idx, final_idx2vtxv, final_vtxv2xy, final_edge2vtxv_wall))
}
