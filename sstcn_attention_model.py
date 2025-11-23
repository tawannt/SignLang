# sstcn_attention_model.py
import torch
import torch.nn as nn
import torch.nn.functional as F

POSE_START, POSE_END = 0, 33
L_HAND_START, L_HAND_END = 33, 54
R_HAND_START, R_HAND_END = 54, 75

class JointAttention(nn.Module):
    def __init__(self, in_channels, num_heads=4):
        super().__init__()
        self.attn = nn.MultiheadAttention(embed_dim=in_channels, num_heads=num_heads, batch_first=True)
    
    def forward(self, x):
        # x: [B, T, J] -> [B, J, T] cho attention
        x = x.permute(0,2,1)
        x, _ = self.attn(x, x, x)
        x = x.permute(0,2,1)  # [B, T, J]
        return x

class SSTCN_Attention(nn.Module):
    def __init__(self, num_classes, num_joints=75, in_channels=3, dropout=0.3):
        super().__init__()
        # --- Spatial conv ---
        self.spatial_conv = nn.Conv1d(in_channels, 128, kernel_size=1)
        self.spatial_bn = nn.BatchNorm1d(128)
        self.spatial_drop = nn.Dropout(dropout)
        
        # --- Attention cho joints tay ---
        self.left_hand_attn = JointAttention(128, num_heads=4)
        self.right_hand_attn = JointAttention(128, num_heads=4)
        
        # --- Temporal conv ---
        self.temporal_conv1 = nn.Conv2d(128, 256, kernel_size=(3,1), padding=(1,0))
        self.temporal_bn1 = nn.BatchNorm2d(256)
        self.temporal_drop1 = nn.Dropout2d(dropout)
        
        self.temporal_conv2 = nn.Conv2d(256, 512, kernel_size=(3,1), padding=(1,0))
        self.temporal_bn2 = nn.BatchNorm2d(512)
        self.temporal_drop2 = nn.Dropout2d(dropout)
        
        # --- Classifier ---
        self.fc_drop = nn.Dropout(dropout)
        self.fc = nn.Linear(512, num_classes)
        
        # Joints tay
        self.left_hand_joints = list(range(L_HAND_START,L_HAND_END))
        self.right_hand_joints = list(range(R_HAND_START,R_HAND_END))
    
    def forward(self, x):
        B, C, T, J = x.shape
        
        # --- Spatial conv ---
        x = x.permute(0,2,1,3).contiguous()  # [B, T, C, J]
        x = x.view(B*T, C, J)                # [B*T, C, J]
        x = F.relu(self.spatial_bn(self.spatial_conv(x)))
        x = self.spatial_drop(x)
        
        # --- Attention cho joints tay --- 
        left_hand = x[:,:,self.left_hand_joints]  # [B*T, 64, 21]
        left_hand = self.left_hand_attn(left_hand)
        right_hand = x[:,:,self.right_hand_joints]
        right_hand = self.right_hand_attn(right_hand)

        # Avoid inplace by clone + scatter
        x_new = x.clone()
        x_new.scatter_(2, torch.tensor(self.left_hand_joints).view(1,1,-1).to(x.device).expand(B*T,128,-1), left_hand)
        x_new.scatter_(2, torch.tensor(self.right_hand_joints).view(1,1,-1).to(x.device).expand(B*T,128,-1), right_hand)
        x = x_new
        
        # --- Khôi phục shape để temporal conv ---
        x = x.view(B, T, 128, J).permute(0,2,1,3)  # [B, 64, T, J]
        
        # --- Temporal conv ---
        x = F.relu(self.temporal_bn1(self.temporal_conv1(x)))
        x = self.temporal_drop1(x)
        x = F.relu(self.temporal_bn2(self.temporal_conv2(x)))
        x = self.temporal_drop2(x)
        
        # Global average pooling (temporal + joints)
        x = x.mean(dim=2).mean(dim=2)  # [B, 256]
        
        # Classifier
        x = self.fc_drop(x)
        out = self.fc(x)  # [B, num_classes]
        return out