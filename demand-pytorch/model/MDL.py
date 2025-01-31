import torch
import torch.nn as nn
import copy


class BasicBlock(nn.Module):
    def __init__(self, in_planes, planes,stride=1):
        super(BasicBlock, self).__init__()
        self.conv1 = nn.Conv2d(in_planes,planes, kernel_size=3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1,bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.relu = nn.ReLU()

    def forward(self, x):
        residual = x
        out = self.bn1(x)
        out = self.relu(out)
        out = self.conv1(out)
        out = self.bn2(out)
        out = self.relu(out)
        out = self.conv2(out)
        out = out + residual
        return out

class STModule(nn.Module):
    def __init__(self,block,conf,nb_residual_unit=2,edge_net=False,k=64):
        super(STModule, self).__init__()
        len_seq, nb_flow, map_height, map_width = conf

        if not edge_net:
            self.conv1 =nn.Conv2d(nb_flow * len_seq, 64, kernel_size=(3, 3), stride=1, padding=1)
            self.layer1 = self._make_layer(block, inplanes=64, planes=64, repetitions=nb_residual_unit)
            self.layer2 = self._make_layer(block, inplanes=64, planes=64, repetitions=nb_residual_unit)
            self.layer3 = self._make_layer(block, inplanes=64, planes=64, repetitions=nb_residual_unit)
            self.conv2 = nn.Conv2d(64, 64, kernel_size=(3, 3), stride=1, padding=1)
        else:
            self.conv1 = nn.Conv2d(k, 128, kernel_size=(3, 3), stride=1, padding=1)
            self.layer1 = self._make_layer(block, inplanes=128, planes=128, repetitions=nb_residual_unit)
            self.layer2 = self._make_layer(block, inplanes=128, planes=128, repetitions=nb_residual_unit)
            self.layer3 = self._make_layer(block, inplanes=128, planes=128, repetitions=nb_residual_unit)
            self.conv2 = nn.Conv2d(128, 64, kernel_size=(3, 3), stride=1, padding=1)

        self.relu = nn.ReLU()



    def _make_layer(self,block,inplanes=64,planes=64,repetitions=5,stride=1):
        layers = []
        for i in range(repetitions):
            layers.append(block(inplanes, planes,stride=stride))
        return nn.Sequential(*layers)

    def forward(self,x):
        out = self.conv1(x)
        out = self.relu(out)
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.conv2(out)
        return out


class FCN(nn.Module):
    def __init__(self,c_conf=(3, 2, 8, 8), p_conf=(1, 2, 8, 8), t_conf=(1, 2, 8, 8),nb_residual_unit=2, embed_dim=16,
                 edge_net=False,block=BasicBlock):
        super(FCN, self).__init__()


        h, w = c_conf[-2], c_conf[-1]
        self.w_c = nn.Parameter(torch.randn(64, h, w))
        self.w_p = nn.Parameter(torch.randn(64, h, w))
        self.w_t = nn.Parameter(torch.randn(64, h, w))
        self.relu = nn.ReLU()

        self.edge_net = edge_net
        self.embed_dim = embed_dim

        if self.edge_net:

            self.embed_c = nn.Conv2d(in_channels=c_conf[0] * c_conf[1], out_channels=self.embed_dim, kernel_size=(1, 1),
                                     stride=1, padding=0, bias=True)
            self.embed_p = nn.Conv2d(in_channels=p_conf[0] * p_conf[1], out_channels=self.embed_dim, kernel_size=(1, 1),
                                     stride=1, padding=0, bias=True)
            self.embed_t = nn.Conv2d(in_channels=t_conf[0] * t_conf[1], out_channels=self.embed_dim, kernel_size=(1, 1),
                                     stride=1, padding=0, bias=True)


            self.c_module = STModule(block, conf=c_conf, nb_residual_unit=nb_residual_unit, edge_net=edge_net,k=self.embed_dim)
            self.p_module = STModule(block, conf=p_conf, nb_residual_unit=nb_residual_unit, edge_net=edge_net,k=self.embed_dim)
            self.t_module = STModule(block, conf=t_conf, nb_residual_unit=nb_residual_unit, edge_net=edge_net,k=self.embed_dim)
        else:
            self.c_module = STModule(block, conf=c_conf, nb_residual_unit=nb_residual_unit, edge_net=edge_net)
            self.p_module = STModule(block, conf=p_conf, nb_residual_unit=nb_residual_unit, edge_net=edge_net)
            self.t_module = STModule(block, conf=t_conf, nb_residual_unit=nb_residual_unit, edge_net=edge_net)

    def forward(self,X_train):
        X_t,X_p,X_c = X_train[0],X_train[1],X_train[2]

        b, t, c, h, w = X_t.shape
        X_t = torch.reshape(X_t,(b,-1,h,w))
        X_p = torch.reshape(X_p,(b,-1,h,w))
        X_c = torch.reshape(X_c,(b,-1,h,w))


        if self.edge_net:


            X_c = self.embed_c(X_c)
            X_p = self.embed_p(X_p)
            X_t = self.embed_t(X_t)

        c_out = self.c_module(X_c)
        p_out = self.p_module(X_p)
        t_out = self.t_module(X_t)
        out = torch.add(self.w_c*c_out,self.w_p*p_out)
        out = torch.add(out,self.w_t*t_out)
        return out



class MDLModel(nn.Module):
    def __init__(self, config):
        super(MDLModel, self).__init__()

        t, c, h, w = config.edge_conf

        self.node_net = FCN(c_conf=config.node_conf, p_conf=config.node_pconf, t_conf=config.node_tconf, nb_residual_unit=2, embed_dim=config.embed_dim, edge_net=False)
        self.edge_net = FCN(c_conf=config.edge_conf, p_conf=config.edge_pconf, t_conf=config.edge_tconf, nb_residual_unit=2, embed_dim=config.embed_dim, edge_net=True)


        # self.bridge = bridge
        self.bridge = config.bridge

        if self.bridge == 'sum':
            self.reduction_dim_conv = nn.Conv2d(in_channels=2*h*w,out_channels=2,kernel_size=1,stride=1,padding=0)

            #用1x1 conv?
            self.node_conv = nn.Conv2d(in_channels=64, out_channels=2, kernel_size=3, stride=1, padding=1)
            self.edge_conv = nn.Conv2d(in_channels=64, out_channels=2 * h * w, kernel_size=3, stride=1, padding=1)
        else:
            self.node_conv = nn.Conv2d(in_channels=128, out_channels=2, kernel_size=3, stride=1, padding=1)
            self.edge_conv = nn.Conv2d(in_channels=128, out_channels=2 * h * w, kernel_size=3, stride=1, padding=1)

        self.external_dim = config.external_dim

        self.fc1 = nn.Linear(in_features=self.external_dim,out_features=10)
        self.fc2 = nn.Linear(in_features=10, out_features=2*h*w)
        self.fc3 = nn.Linear(in_features=10, out_features=2*((h*w)**2))

        self.mse = nn.MSELoss()
        self.mae = nn.L1Loss()
        self.relu = nn.ReLU()
        self.w_node = 1
        self.w_edge = 1
        self.w_mdl = 0.0005

    def fusion_external(self, X_ext, flow, planel,edge_net=False):
        b, c, h, w = flow.shape
        if self.external_dim != None and self.external_dim > 0:
            external_out = self.fc1(X_ext)
            external_out = self.relu(external_out)
            if not edge_net:
                external_out = self.fc2(external_out)
            else:
                external_out = self.fc3(external_out)
            external_out = self.relu(external_out)
            external_out = external_out.reshape(external_out.shape[0], planel, h, w)
        else:
            print('external_dim:', self.external_dim)
        # gating
        external_out = torch.sigmoid(external_out)

        #formular 10
        out = external_out * flow
        out = torch.tanh(out)

        return out

    def forward(self,X,M,X_ext):
        '''
        :param X: the node net input,shape (b,c,h,w)
        :param M: the edge net input,shape (b,c',h,w), c' = h*w*2
        :param X_ext: external imformation,shape(b,f),f is external dim
        :return:
        '''
        node_flow = self.node_net(X)
        edge_flow = self.edge_net(M)
        #todo cross concat
        if self.bridge == 'concat':
            fusion_flow = torch.cat([node_flow,edge_flow],dim=1)

            #to fusion external
            node_out = self.node_conv(fusion_flow)
            edge_out = self.edge_conv(fusion_flow)

        elif self.bridge == 'sum':
            edge_flow = self.reduction_dim_conv(edge_flow)
            fusion_flow = torch.add(node_flow, edge_flow)

            node_out = self.node_conv(fusion_flow)
            edge_out = self.edge_conv(fusion_flow)

        node_out = self.fusion_external(X_ext, node_out, planel=2)
        edge_out = self.fusion_external(X_ext, edge_out, planel=2 * M[0].shape[-2] * M[0].shape[-1], edge_net=True)


        return node_out,edge_out


    def multask_loss(self, X, M, X_ext, X_gt, M_gt, X_scaler, M_scaler):

        node_pred, edge_pred = self.forward(X,M,X_ext)

        node_pred = X_scaler.inverse_transform(node_pred)
        edge_pred = M_scaler.inverse_transform(edge_pred)


        # indication matrix
        P_node = copy.deepcopy(X_gt)
        P_node[P_node > 0] = 1

        Q_edge = copy.deepcopy(M_gt)
        Q_edge[Q_edge > 0] = 1

        #node_loss & edge_loss
        #node_loss = torch.sum(torch.square(P_node*(X_gt-node_pred)))
        #edge_loss = torch.sum(torch.square(Q_edge*(M_gt-edge_pred)))

        node_loss = torch.mul(torch.sum(P_node*(X_gt-node_pred)*(X_gt-node_pred)),self.w_node)
        edge_loss = torch.mul(torch.sum(Q_edge*(M_gt-edge_pred)*(M_gt-edge_pred)),self.w_edge)

        #print("node, edge: ", node_loss, edge_loss)

        #mdl loss
        #out flow - outgoing transitions
        out_loss = X_gt[:,0,:,:] - torch.sum(M_gt[:,:M_gt.shape[-1]*M_gt.shape[-2],:,:],dim=1)
        # in flow - incoming transitions
        in_loss = X_gt[:,1,:,:] - torch.sum(M_gt[:,M_gt.shape[-1]*M_gt.shape[-2]:,:,:],dim=1)
        mdl_loss = torch.sum(out_loss*out_loss+in_loss*in_loss)

        loss_all = self.w_node * node_loss + self.w_edge * edge_loss + self.w_mdl * mdl_loss

        # node_rmse = torch.sqrt(self.mse(node_pred,X_gt))
        # edge_rmse = torch.sqrt(self.mse(edge_pred,M_gt))
        #
        # node_mae = self.mae(node_pred,X_gt)
        # edge_mae = self.mae(edge_pred,M_gt)

        return loss_all, node_pred, edge_pred

